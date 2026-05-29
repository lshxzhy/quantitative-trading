from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import csv
import io
import os
import re
import zipfile

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
PROFILE_DIR = PROJECT_ROOT / "state" / "chrome_profile"

WEBVPN_URL = "https://webvpn.swufe.edu.cn/"
WEBVPN_SEARCH_XPATH = '//*[@id="__layout"]/div/div/div[2]/div/div/input'
CSMAR_URL = "https://data.csmar.com/"
STOCK_MARKET_ROUTE = "/datacenter/singletable/search?databaseId=63&tbId=4"
INDEX_MARKET_ROUTE = "/datacenter/singletable/search?databaseId=42&tbId=45"

STOCK_DATASET_NAME = "日个股回报率文件"
INDEX_DATASET_NAME = "国内指数日行情文件"
STOCK_MARKET_DATABASE_NAME = "股票市场交易"
INDEX_MARKET_DATABASE_NAME = "市场指数"
INDEX_CODES = ("000001", "000300", "000852", "000905")
INDEX_CODE_SEARCH_TERMS = {
    "000001": ("000001", "上证综合"),
    "000300": ("000300", "沪深300"),
    "000852": ("中证1000", "000852"),
    "000905": ("中证500", "000905"),
}
INDEX_DATE_FIELD = "Idxtrd01"

HOME_SEARCH_PLACEHOLDER = "请输入关键字"
STOCK_MAX_YEARS_PER_REQUEST = 5
INDEX_MAX_YEARS_PER_REQUEST = 4
DOWNLOAD_TIMEOUT_SECONDS = 1800

load_dotenv(ENV_PATH, override=True)

DATASET_KIND = os.getenv("CSMAR_DATASET_KIND", "stock").strip().lower()
DOWNLOAD_MODE = os.getenv("CSMAR_DOWNLOAD_MODE", "full").strip().lower()
USERNAME = os.getenv("WEBVPN_USERNAME")
PASSWORD = os.getenv("WEBVPN_PASSWORD")

if DATASET_KIND not in {"stock", "index"}:
    raise RuntimeError('CSMAR_DATASET_KIND 只能是 "stock" 或 "index"')

if DOWNLOAD_MODE not in {"full", "update"}:
    raise RuntimeError('CSMAR_DOWNLOAD_MODE 只能是 "full" 或 "update"')

START_DATE = date(2004, 1, 1)

if DATASET_KIND == "stock":
    DATASET_NAME = STOCK_DATASET_NAME
    DOWNLOAD_DIR = PROJECT_ROOT / "data" / "raw" / "stocks"
else:
    DATASET_NAME = INDEX_DATASET_NAME
    DOWNLOAD_DIR = PROJECT_ROOT / "data" / "raw" / "indexes"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

driver: webdriver.Chrome
wait: WebDriverWait


def log(message: str) -> None:
    print(f"[CSMAR] {message}", flush=True)


def is_visible(element: WebElement) -> bool:
    try:
        return element.is_displayed()
    except StaleElementReferenceException:
        return False


def first_visible(elements: list[WebElement]) -> WebElement | bool:
    for element in elements:
        if is_visible(element):
            return element
    return False


def first_clickable(elements: list[WebElement]) -> WebElement | bool:
    for element in elements:
        if is_visible(element) and element.is_enabled():
            return element
    return False


def click(element: WebElement) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    driver.execute_script("arguments[0].click();", element)


def required_visible(by: str, selector: str) -> WebElement:
    return wait.until(lambda _: first_visible(driver.find_elements(by, selector)))


def required_clickable(by: str, selector: str) -> WebElement:
    return wait.until(lambda _: first_clickable(driver.find_elements(by, selector)))


def visible_buttons(text: str, scope: WebElement | webdriver.Chrome | None = None) -> list[WebElement]:
    root = scope or driver
    prefix = ".//" if scope else "//"
    xpath = f"{prefix}button[normalize-space()='{text}' or .//span[normalize-space()='{text}']]"
    return [
        button
        for button in root.find_elements(By.XPATH, xpath)
        if is_visible(button) and button.is_enabled()
    ]


def required_button(text: str, scope: WebElement | webdriver.Chrome | None = None) -> WebElement:
    return wait.until(lambda _: first_clickable(visible_buttons(text, scope)))


def optional_click_text(text: str) -> None:
    for element in driver.find_elements(By.XPATH, f"//*[normalize-space()='{text}']"):
        if is_visible(element):
            click(element)
            return


def optional_click_contains_text(text: str) -> bool:
    xpath = (
        "//*[self::button or self::a or self::span or self::input]"
        f"[contains(normalize-space(), '{text}') or contains(@value, '{text}')]"
    )
    for element in driver.find_elements(By.XPATH, xpath):
        if is_visible(element) and element.is_enabled():
            click(element)
            return True

    return False


def handle_single_session_prompt() -> bool:
    try:
        clicked = WebDriverWait(driver, 8).until(
            lambda _: optional_click_contains_text("踢出以上会话") or webvpn_portal_is_open()
        )
    except TimeoutException:
        return False

    if clicked and not webvpn_portal_is_open():
        wait.until(lambda _: webvpn_portal_is_open() or webvpn_login_form_is_open())

    return bool(clicked)


def webvpn_portal_is_open() -> bool:
    return bool(first_visible(driver.find_elements(By.XPATH, WEBVPN_SEARCH_XPATH)))


def webvpn_login_form_is_open() -> bool:
    return bool(first_visible(driver.find_elements(By.XPATH, '//*[@id="username"]')))


def csmar_page_is_open() -> bool:
    return (
        ("csmar.html" in driver.current_url or driver.title == "CSMAR")
        and not webvpn_login_form_is_open()
    )


def login_webvpn() -> None:
    if not USERNAME or not PASSWORD:
        raise RuntimeError(".env 中缺少 WEBVPN_USERNAME 或 WEBVPN_PASSWORD")

    driver.get(WEBVPN_URL)
    wait.until(lambda _: webvpn_portal_is_open() or webvpn_login_form_is_open())

    if webvpn_portal_is_open():
        return

    elements = driver.find_elements(By.XPATH, '//*[@id="username"]')
    if elements:
        elements[0].send_keys(USERNAME)
        driver.find_element(By.XPATH, '//*[@id="password"]').send_keys(PASSWORD)
        driver.find_element(By.XPATH, '//*[@id="login_submit"]').click()

    handle_single_session_prompt()

    elements = driver.find_elements(By.XPATH, "/html/body/div[1]/div/div/div/div[2]/input[1]")
    if elements:
        elements[0].click()

    elements = driver.find_elements(By.XPATH, '//*[@id="getDynamicCode"]')
    if elements:
        elements[0].click()
        input("请手动输入验证码，完成后在这里按回车继续：")

    elements = driver.find_elements(By.XPATH, "/html/body/div/div[1]/div[2]/div[2]/div[1]/div[4]/button")
    if elements:
        elements[0].click()

    elements = driver.find_elements(By.XPATH, '//*[@id="bg"]/div/div[5]/div/div/div[3]/button[2]/span')
    if elements:
        elements[0].click()

    required_visible(By.XPATH, WEBVPN_SEARCH_XPATH)


def switch_to_existing_csmar() -> bool:
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if csmar_page_is_open():
            driver.switch_to.default_content()
            wait.until(lambda _: csmar_page_is_open())
            handle_optional_csmar_popups()
            return True

    return False


def open_csmar() -> None:
    if switch_to_existing_csmar():
        return

    old_handles = set(driver.window_handles)
    search_box = required_clickable(By.XPATH, WEBVPN_SEARCH_XPATH)
    search_box.send_keys(CSMAR_URL)
    search_box.send_keys(Keys.ENTER)

    new_handle = wait.until(lambda _: next(iter(set(driver.window_handles) - old_handles), False))
    driver.switch_to.window(new_handle)
    driver.switch_to.default_content()

    if "csmar.html" not in driver.current_url:
        iframe = required_visible(By.CSS_SELECTOR, "iframe[src*='csmar.html']")
        iframe_src = iframe.get_dom_attribute("src")
        if not iframe_src:
            raise RuntimeError("CSMAR iframe 没有 src")
        driver.get(driver.current_url.rstrip("/") + "/" + iframe_src.lstrip("/"))

    wait.until(lambda _: "CSMAR" in driver.title or "csmar.html" in driver.current_url)


def handle_optional_csmar_popups() -> None:
    optional_click_text("我知道了")

    for icon in driver.find_elements(By.CSS_SELECTOR, "i.icon-shanchu1"):
        if is_visible(icon):
            click(icon)
            break

    relogin_buttons = visible_buttons("重新登录")
    if relogin_buttons:
        click(relogin_buttons[0])


def go_to_csmar_home() -> None:
    base_url = driver.current_url.split("#", 1)[0]
    driver.get(f"{base_url}#/index")
    required_visible(By.CSS_SELECTOR, f"input[placeholder='{HOME_SEARCH_PLACEHOLDER}']")
    handle_optional_csmar_popups()


def open_single_table_page(
    route: str,
    database_name: str,
    table_name: str,
    label: str,
) -> None:
    log(f"打开{database_name} - {label}页面")
    last_error: Exception | None = None

    for attempt in range(3):
        base_url = driver.current_url.split("#", 1)[0]
        driver.get(f"{base_url}#{route}")
        try:
            route_query = route.split("?", 1)[1]
            WebDriverWait(driver, 15).until(
                lambda _: (
                    "/datacenter/singletable/search" in driver.current_url
                    and route_query in driver.current_url
                )
            )
            WebDriverWait(driver, 20).until(
                lambda _: (
                    database_name in driver.find_element(By.TAG_NAME, "body").text
                    and table_name in driver.find_element(By.TAG_NAME, "body").text
                )
            )
            return
        except TimeoutException as error:
            last_error = error
            log(f"{label}直达未稳定进入单表页，重试 {attempt + 1}/3")
            go_to_csmar_home()

    raise RuntimeError(f"无法打开{database_name} - {label}页面") from last_error


def open_stock_market_page() -> None:
    open_single_table_page(
        STOCK_MARKET_ROUTE,
        STOCK_MARKET_DATABASE_NAME,
        STOCK_DATASET_NAME,
        "日个股回报率文件",
    )


def select_dataset() -> None:
    if DATASET_KIND == "stock":
        open_stock_market_page()
        wait.until(lambda _: STOCK_DATASET_NAME in driver.find_element(By.TAG_NAME, "body").text)
        return

    open_market_index_page()


def open_market_index_page() -> None:
    open_single_table_page(
        INDEX_MARKET_ROUTE,
        INDEX_MARKET_DATABASE_NAME,
        INDEX_DATASET_NAME,
        "国内指数日行情文件",
    )


def visible_dialog() -> WebElement | bool:
    return first_visible(driver.find_elements(By.CSS_SELECTOR, ".el-dialog"))


def select_all_a_share_codes() -> None:
    log("选择全部 A 股代码")
    click(required_button("代码选择"))

    dialog = wait.until(lambda _: visible_dialog())
    tree_nodes = wait.until(
        lambda _: [
            node
            for node in dialog.find_elements(By.CSS_SELECTOR, ".symbol-list .el-tree-node")
            if is_visible(node)
        ]
    )

    first_tree_node = tree_nodes[0]
    if "is-expanded" not in first_tree_node.get_attribute("class"):
        click(first_tree_node.find_element(By.CSS_SELECTOR, ".el-tree-node__expand-icon"))

    tree_contents = wait.until(visible_code_tree_contents)
    click(tree_contents[1])

    wait.until(code_candidates_loaded)
    click(required_button("全选", dialog))
    click(required_button("确定", dialog))
    wait.until(lambda _: not visible_dialog())


def select_target_index_codes() -> None:
    log("选择目标市场指数代码：" + ", ".join(INDEX_CODES))
    click(required_button("代码选择"))

    dialog = wait.until(lambda _: visible_dialog())
    for code in INDEX_CODES:
        select_index_code(dialog, code)

    wait.until(lambda _: set(INDEX_CODES).issubset(selected_index_codes(dialog)))
    click(required_button("确定", dialog))
    wait.until(lambda _: not visible_dialog())


def select_index_code(dialog: WebElement, code: str) -> None:
    if code in selected_index_codes(dialog):
        log(f"指数代码 {code} 已在已选列表中")
        return

    for search_term in INDEX_CODE_SEARCH_TERMS[code]:
        search_box = index_code_search_input(dialog)
        search_box.send_keys(Keys.CONTROL, "a")
        search_box.send_keys(Keys.BACKSPACE)
        search_box.send_keys(search_term)
        search_box.send_keys(Keys.ENTER)

        try:
            add_button = WebDriverWait(driver, 8).until(
                lambda _: first_clickable(visible_index_code_add_buttons(dialog, code))
            )
        except TimeoutException:
            continue

        click(add_button)
        wait.until(lambda _: code in selected_index_codes(dialog))
        log(f"已选择指数代码 {code}（搜索：{search_term}）")
        return

    raise RuntimeError(f"未找到指数代码 {code}")


def index_code_search_input(dialog: WebElement) -> WebElement:
    return wait.until(
        lambda _: first_clickable(
            [
                item
                for item in dialog.find_elements(By.CSS_SELECTOR, "input.el-input__inner")
                if is_visible(item) and item.rect.get("width", 0) > 180
            ]
        )
    )


def selected_index_codes(dialog: WebElement) -> set[str]:
    selected_area = dialog.find_elements(By.CSS_SELECTOR, ".select-list.last")
    if not selected_area:
        return set()

    return set(re.findall(r"\b\d{6}\b", selected_area[0].text))


def visible_index_code_add_buttons(dialog: WebElement, code: str) -> list[WebElement]:
    xpath = (
        ".//div[contains(@class, 'wait-list-item')]"
        "[.//span[starts-with(normalize-space(), '"
        + code
        + "（')]]"
        "//i[contains(@class, 'el-icon-circle-plus-outline')]"
    )
    return [
        item
        for item in dialog.find_elements(By.XPATH, xpath)
        if is_visible(item) and item.is_enabled()
    ]


def visible_code_tree_contents(_: webdriver.Chrome) -> list[WebElement] | bool:
    dialog = visible_dialog()
    if not dialog:
        return False

    tree_contents = [
        item
        for item in dialog.find_elements(By.CSS_SELECTOR, ".symbol-list .el-tree-node__content")
        if is_visible(item)
    ]
    return tree_contents if len(tree_contents) > 1 else False


def code_candidates_loaded(_: webdriver.Chrome) -> bool:
    dialog = visible_dialog()
    if not dialog:
        return False

    dialog_text = dialog.text
    if re.search(r"\b\d{6}\b", dialog_text):
        return True

    values = [
        item.get_attribute("value") or ""
        for item in dialog.find_elements(By.CSS_SELECTOR, "input, textarea")
    ]
    return any(re.search(r"\b\d{6}\b", value) for value in values)


def select_all_fields() -> None:
    log("选择全部字段")
    wait.until(lambda _: "字段" in driver.find_element(By.TAG_NAME, "body").text)
    click(required_button("全选"))


def select_csv_format() -> None:
    log("选择标准 CSV 下载格式")
    csv_label = wait.until(
        lambda _: first_clickable(
            driver.find_elements(
                By.XPATH,
                "//label[contains(@class, 'el-radio')"
                " and contains(normalize-space(), 'CSV格式')"
                " and contains(normalize-space(), '*.csv')"
                " and not(contains(normalize-space(), 'Matlab'))]",
            )
        )
    )
    click(csv_label)
    wait.until(standard_csv_is_checked)


def standard_csv_is_checked(_: webdriver.Chrome) -> bool:
    labels = driver.find_elements(
        By.XPATH,
        "//label[contains(@class, 'el-radio')"
        " and contains(normalize-space(), 'CSV格式')"
        " and contains(normalize-space(), '*.csv')"
        " and not(contains(normalize-space(), 'Matlab'))]",
    )

    for label in labels:
        if not is_visible(label):
            continue
        if "is-checked" in label.get_attribute("class"):
            return True
        if label.find_elements(By.CSS_SELECTOR, "input:checked"):
            return True

    return False


def parse_latest_data_date() -> date:
    body_text = driver.find_element(By.TAG_NAME, "body").text
    match = re.search(
        r"数据结束时间\s*[:：]?\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})",
        body_text,
    )
    if not match:
        raise RuntimeError("没有从页面中解析到数据结束时间")

    year, month, day = map(int, match.groups())
    return date(year, month, day)


def date_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start
    max_years = INDEX_MAX_YEARS_PER_REQUEST if DATASET_KIND == "index" else STOCK_MAX_YEARS_PER_REQUEST

    while current <= end:
        next_start = current.replace(year=current.year + max_years)
        current_end = min(next_start - timedelta(days=1), end)
        ranges.append((current, current_end))
        current = current_end + timedelta(days=1)

    return ranges


def set_vue_input(element: WebElement, value: str) -> None:
    driver.execute_script(
        """
        const input = arguments[0];
        input.scrollIntoView({block: "center"});
        input.removeAttribute("readonly");
        input.focus();
        """,
        element,
    )

    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(value)
    element.send_keys(Keys.ENTER)

    driver.execute_script(
        """
        const input = arguments[0];
        const value = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype,
            "value"
        ).set;

        input.removeAttribute("readonly");
        setter.call(input, value);
        input.dispatchEvent(new Event("input", {bubbles: true}));
        input.dispatchEvent(new Event("change", {bubbles: true}));

        let component = input.closest(".el-date-editor")?.__vue__;
        const visited = new Set();
        while (component && !visited.has(component)) {
            visited.add(component);
            const name = component.$options?.name || component.$options?._componentTag || "";
            if (/DatePicker/i.test(name)) {
                if (typeof component.emitInput === "function") {
                    component.emitInput(value);
                }
                component.$emit("input", value);
                component.$emit("change", value);
                if ("userInput" in component) {
                    component.userInput = null;
                }
                break;
            }
            component = component.$parent;
        }

        input.blur();
        """,
        element,
        value,
    )
    wait.until(lambda _: element.get_attribute("value") == value)


def visible_date_inputs() -> list[WebElement]:
    inputs = []

    for item in driver.find_elements(By.CSS_SELECTOR, "input.el-input__inner"):
        if is_visible(item) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.get_attribute("value") or ""):
            inputs.append(item)

    return inputs


def set_download_date_range(start: date, end: date) -> None:
    date_inputs = wait.until(lambda _: visible_date_inputs() if len(visible_date_inputs()) >= 2 else False)
    set_vue_input(date_inputs[0], start.isoformat())
    set_vue_input(date_inputs[1], end.isoformat())


def download_has_started(before_files: set[str]) -> bool:
    if list(DOWNLOAD_DIR.glob("*.crdownload")):
        return True

    return any(
        path.is_file() and path.name not in before_files and path.suffix.lower() != ".crdownload"
        for path in DOWNLOAD_DIR.iterdir()
    )


def switch_to_download_result_page(query_handle: str, old_handles: set[str]) -> str:
    def result_page(_: webdriver.Chrome) -> str | bool:
        handles = [handle for handle in driver.window_handles if handle not in old_handles]
        handles.append(query_handle)

        for handle in handles:
            driver.switch_to.window(handle)
            if "sdownload.html" in driver.current_url:
                return handle

        return False

    return WebDriverWait(driver, DOWNLOAD_TIMEOUT_SECONDS, poll_frequency=1).until(result_page)


def visible_zip_links() -> list[WebElement]:
    xpath = (
        "//a["
        "contains(normalize-space(), '.zip')"
        " or contains(@href, '.zip')"
        f" or contains(normalize-space(), '{DATASET_NAME}')"
        "]"
    )
    return [
        link
        for link in driver.find_elements(By.XPATH, xpath)
        if is_visible(link) and link.is_enabled()
    ]


def click_result_zip_link(before_files: set[str]) -> None:
    result_wait = WebDriverWait(driver, DOWNLOAD_TIMEOUT_SECONDS, poll_frequency=1)
    click(result_wait.until(lambda _: first_clickable(visible_zip_links())))
    result_wait.until(lambda _: download_has_started(before_files))


def wait_for_download(before_files: set[str]) -> Path:
    sizes: dict[Path, int] = {}
    download_wait = WebDriverWait(driver, DOWNLOAD_TIMEOUT_SECONDS, poll_frequency=1)

    def completed_file(_: webdriver.Chrome) -> Path | bool:
        if list(DOWNLOAD_DIR.glob("*.crdownload")):
            return False

        files = [
            path
            for path in DOWNLOAD_DIR.iterdir()
            if path.is_file()
            and path.name not in before_files
            and path.suffix.lower() != ".crdownload"
        ]
        if not files:
            return False

        newest_file = max(files, key=lambda path: path.stat().st_mtime)
        current_size = newest_file.stat().st_size
        previous_size = sizes.get(newest_file)
        sizes[newest_file] = current_size

        return newest_file if previous_size == current_size and current_size > 0 else False

    return download_wait.until(completed_file)


def numbered_file(index: int, suffix: str = ".zip") -> Path:
    return DOWNLOAD_DIR / f"{index}{suffix.lower()}"


def replace_with_numbered_file(downloaded_file: Path, index: int) -> Path:
    suffix = downloaded_file.suffix or ".zip"
    target_file = numbered_file(index, suffix)

    for old_file in DOWNLOAD_DIR.glob(f"{index}.*"):
        if old_file.resolve() != downloaded_file.resolve():
            old_file.unlink()

    if downloaded_file.resolve() != target_file.resolve():
        downloaded_file.replace(target_file)

    return target_file


def completed_numbered_file(index: int) -> Path | None:
    matches = [
        path
        for path in DOWNLOAD_DIR.glob(f"{index}.*")
        if path.is_file() and path.stat().st_size > 0 and path.suffix.lower() != ".crdownload"
    ]
    return matches[0] if matches else None


def numbered_zip_files() -> list[Path]:
    return sorted(
        [
            path
            for path in DOWNLOAD_DIR.glob("*.zip")
            if path.is_file() and path.stem.isdigit() and int(path.stem) > 0
        ],
        key=lambda path: int(path.stem),
    )


def next_numbered_index(files: list[Path]) -> int:
    if not files:
        return 1

    return max(int(file.stem) for file in files if file.stem.isdigit()) + 1


def latest_downloaded_date(files: list[Path]) -> date | None:
    dates = [
        latest_date_in_zip(file)
        for file in files
    ]
    dates = [item for item in dates if item]
    return max(dates) if dates else None


def latest_date_in_zip(zip_path: Path) -> date | None:
    latest: date | None = None
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        for csv_name in csv_names:
            text, _ = decode_csv_bytes(archive.read(csv_name))
            reader = csv.DictReader(io.StringIO(text))
            field = row_date_field(set(reader.fieldnames or []))
            if not field:
                continue

            for row in reader:
                value = row.get(field)
                if not value:
                    continue
                row_date = date.fromisoformat(value)
                latest = row_date if latest is None else max(latest, row_date)

    return latest


def row_date_field(fieldnames: set[str]) -> str | None:
    if DATASET_KIND == "stock" and "Trddt" in fieldnames:
        return "Trddt"
    if DATASET_KIND == "index" and INDEX_DATE_FIELD in fieldnames:
        return INDEX_DATE_FIELD

    return None


def download_current_page(index: int, start: date | None = None, end: date | None = None) -> Path:
    existing_file = completed_numbered_file(index)
    if existing_file and zip_is_valid(existing_file, start, end):
        log(f"跳过 {existing_file.name}，已有文件校验通过")
        return existing_file
    if existing_file:
        log(f"删除未通过校验的旧文件：{existing_file.name}")
        existing_file.unlink()

    label = f"{start} 至 {end}" if start and end else "当前页面条件"
    log(f"开始下载第 {index} 段：{label}")
    query_handle = driver.current_window_handle
    old_handles = set(driver.window_handles)
    before_files = {path.name for path in DOWNLOAD_DIR.iterdir() if path.is_file()}

    click(required_button("下载数据"))
    result_handle = switch_to_download_result_page(query_handle, old_handles)
    click_result_zip_link(before_files)

    downloaded_file = wait_for_download(before_files)
    target_file = replace_with_numbered_file(downloaded_file, index)
    postprocess_zip(target_file, start, end)
    log(f"完成下载并校验：{target_file.name}")

    if result_handle != query_handle and result_handle in driver.window_handles:
        driver.close()
        driver.switch_to.window(query_handle)

    return target_file


def download_current_range(index: int, start: date, end: date) -> Path:
    set_download_date_range(start, end)
    return download_current_page(index, start, end)


def csv_name_in_zip(zip_path: Path) -> str:
    return csv_names_in_zip(zip_path)[0]


def csv_names_in_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]

    if not csv_names:
        raise RuntimeError(f"{zip_path.name} 中没有 CSV 文件")

    return csv_names


def decode_csv_bytes(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise RuntimeError("无法识别 CSMAR CSV 编码")


def postprocess_zip(zip_path: Path, start: date | None, end: date | None) -> None:
    if DATASET_KIND == "index":
        filter_index_zip(zip_path)

    if not zip_is_valid(zip_path, start, end):
        raise RuntimeError(f"{zip_path.name} 下载后校验失败")


def filter_index_zip(zip_path: Path) -> None:
    target_codes = set(INDEX_CODES)
    temp_file = zip_path.with_suffix(".tmp")
    kept_rows_count = 0

    with zipfile.ZipFile(zip_path) as source, zipfile.ZipFile(
        temp_file,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.lower().endswith(".csv"):
                text, encoding = decode_csv_bytes(data)
                reader = csv.DictReader(io.StringIO(text))
                if not reader.fieldnames or "Indexcd" not in reader.fieldnames:
                    raise RuntimeError(f"{zip_path.name} 缺少 Indexcd 字段")

                rows = [
                    row
                    for row in reader
                    if (row.get("Indexcd") or "").zfill(6) in target_codes
                ]
                kept_rows_count += len(rows)

                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=reader.fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                data = buffer.getvalue().encode(encoding)

            target.writestr(item, data)

    if kept_rows_count == 0:
        temp_file.unlink(missing_ok=True)
        raise RuntimeError(f"{zip_path.name} 没有筛选到目标指数")

    temp_file.replace(zip_path)


def zip_is_valid(zip_path: Path, start: date | None = None, end: date | None = None) -> bool:
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        return False

    try:
        with zipfile.ZipFile(zip_path) as archive:
            if DATASET_KIND == "stock":
                csv_name = csv_name_in_zip(zip_path)
                with archive.open(csv_name) as csv_file:
                    text, _ = decode_csv_bytes(csv_file.read(65536))
            else:
                rows, fieldnames = index_rows_in_archive(archive)
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False

    if DATASET_KIND == "stock":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return False
        return {"Stkcd", "Trddt"}.issubset(reader.fieldnames) and next(reader, None) is not None

    if "Indexcd" not in fieldnames or INDEX_DATE_FIELD not in fieldnames:
        return False

    if not rows:
        return False

    codes = {(row.get("Indexcd") or "").zfill(6) for row in rows}
    if codes - set(INDEX_CODES):
        return False

    if start and end:
        try:
            dates = [
                date.fromisoformat(row[INDEX_DATE_FIELD])
                for row in rows
                if row.get(INDEX_DATE_FIELD)
            ]
        except ValueError:
            return False
        if not dates or min(dates) < start or max(dates) > end:
            return False

    return True


def index_rows_in_archive(archive: zipfile.ZipFile) -> tuple[list[dict[str, str]], set[str]]:
    rows: list[dict[str, str]] = []
    fieldnames: set[str] = set()
    csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if not csv_names:
        raise RuntimeError("zip 中没有 CSV 文件")

    for csv_name in csv_names:
        text, _ = decode_csv_bytes(archive.read(csv_name))
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise RuntimeError(f"{csv_name} 缺少表头")
        csv_fieldnames = set(reader.fieldnames)
        if "Indexcd" not in csv_fieldnames or INDEX_DATE_FIELD not in csv_fieldnames:
            raise RuntimeError(f"{csv_name} 缺少 Indexcd 或 {INDEX_DATE_FIELD} 字段")
        fieldnames.update(reader.fieldnames)
        rows.extend(reader)

    return rows, fieldnames


def index_codes_in_zip(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as archive:
        rows, _ = index_rows_in_archive(archive)

    return {
        (row.get("Indexcd") or "").zfill(6)
        for row in rows
        if row.get("Indexcd")
    }


def validate_downloaded_files(files: list[Path]) -> None:
    if DATASET_KIND != "index":
        return

    codes = set()
    for file in files:
        codes.update(index_codes_in_zip(file))

    missing_codes = set(INDEX_CODES) - codes
    if missing_codes:
        missing_text = ", ".join(sorted(missing_codes))
        raise RuntimeError(f"指数下载结果缺少目标指数: {missing_text}")
    log("指数下载结果校验通过，目标指数齐全：" + ", ".join(sorted(codes & set(INDEX_CODES))))


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--start-maximized")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(DOWNLOAD_DIR),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
        },
    )

    browser = webdriver.Chrome(options=options)
    browser.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": str(DOWNLOAD_DIR)},
    )
    browser.implicitly_wait(1)
    return browser


def prepare_download_page() -> None:
    log(f"数据类型：{DATASET_KIND}；下载模式：{DOWNLOAD_MODE}；下载目录：{DOWNLOAD_DIR}")
    if not switch_to_existing_csmar():
        log("按个股爬虫相同流程打开 WebVPN/CSMAR")
        login_webvpn()
        open_csmar()
    else:
        log("复用当前 Chrome profile 中已有的 CSMAR 会话")
    select_dataset()
    if DATASET_KIND == "stock":
        select_all_a_share_codes()
    else:
        select_target_index_codes()
    select_all_fields()
    select_csv_format()


def run_downloads() -> None:
    latest_date = parse_latest_data_date()
    log(f"页面数据结束日期：{latest_date}")

    if DOWNLOAD_MODE == "update":
        run_update_download(latest_date)
        return

    run_full_download(latest_date)


def run_full_download(latest_date: date) -> None:
    downloaded_files = []
    for index, (start, end) in enumerate(date_ranges(START_DATE, latest_date), start=1):
        log(f"处理第 {index} 段日期：{start} 至 {end}")
        downloaded_files.append(download_current_range(index, start, end))

    validate_downloaded_files(downloaded_files)


def run_update_download(latest_date: date) -> None:
    existing_files = [
        file
        for file in numbered_zip_files()
        if zip_is_valid(file)
    ]
    local_latest_date = latest_downloaded_date(existing_files)

    if not local_latest_date:
        log("没有可用本地文件，改为全量下载")
        run_full_download(latest_date)
        return

    if local_latest_date >= latest_date:
        log(f"本地数据已到最新日期：{local_latest_date}")
        validate_downloaded_files(existing_files)
        return

    update_start = local_latest_date + timedelta(days=1)
    next_index = next_numbered_index(existing_files)
    downloaded_files = []
    for offset, (start, end) in enumerate(date_ranges(update_start, latest_date)):
        index = next_index + offset
        log(f"更新第 {index} 段日期：{start} 至 {end}")
        downloaded_files.append(download_current_range(index, start, end))

    validate_downloaded_files(existing_files + downloaded_files)


def main() -> None:
    global driver, wait

    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:
        prepare_download_page()
        run_downloads()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
