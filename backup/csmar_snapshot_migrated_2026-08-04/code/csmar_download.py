"""Archived Selenium crawler for the CSMAR data snapshot."""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


def log(message: str) -> None:
    print(f"[CSMAR] {message}", flush=True)


def split_date_range(start: date, end: date, years: int) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start

    while current <= end:
        next_year = current.year + years
        next_day = min(current.day, monthrange(next_year, current.month)[1])
        next_start = current.replace(year=next_year, day=next_day)
        current_end = min(next_start - timedelta(days=1), end)
        ranges.append((current, current_end))
        current = current_end + timedelta(days=1)

    return ranges


def csv_members(archive: zipfile.ZipFile) -> list[str]:
    members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if not members:
        raise RuntimeError("下载的 ZIP 中没有 CSV 文件")
    return members


def numbered_archives(directory: Path) -> list[Path]:
    archives = list(directory.glob("*.zip"))
    if not archives:
        raise RuntimeError(f"{directory} 中没有历史 ZIP，增量更新无法确定起始日期")

    invalid_names = [path.name for path in archives if not path.stem.isdigit()]
    if invalid_names:
        raise RuntimeError("ZIP 文件必须按数字命名：" + ", ".join(sorted(invalid_names)))

    archives.sort(key=lambda path: int(path.stem))
    actual_numbers = [int(path.stem) for path in archives]
    expected_numbers = list(range(1, actual_numbers[-1] + 1))
    if actual_numbers != expected_numbers:
        raise RuntimeError(
            f"{directory} 中的 ZIP 编号不连续：实际 {actual_numbers}，"
            f"预期 {expected_numbers}"
        )
    return archives


def cached_chromedriver() -> Path:
    with OpenKey(HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
        chrome_version = str(QueryValueEx(key, "version")[0])
    chrome_major = chrome_version.split(".", 1)[0]

    driver_root = Path.home() / ".cache" / "selenium" / "chromedriver" / "win64"
    candidates = [
        path / "chromedriver.exe"
        for path in driver_root.glob(f"{chrome_major}.*")
        if (path / "chromedriver.exe").is_file()
    ]
    if not candidates:
        raise RuntimeError(
            f"没有找到与 Chrome {chrome_version} 同主版本的缓存 ChromeDriver；"
            "请先安装匹配的 ChromeDriver"
        )

    return max(
        candidates,
        key=lambda path: tuple(int(part) for part in path.parent.name.split(".")),
    )


def latest_local_date(directory: Path, date_field: str) -> tuple[date, int]:
    archives = numbered_archives(directory)
    latest: date | None = None

    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            for member in csv_members(archive):
                with archive.open(member) as binary_file:
                    text_file = io.TextIOWrapper(
                        binary_file,
                        encoding="utf-8-sig",
                        newline="",
                    )
                    reader = csv.DictReader(text_file)
                    if not reader.fieldnames or date_field not in reader.fieldnames:
                        raise RuntimeError(
                            f"{archive_path.name}:{member} 缺少 {date_field} 字段"
                        )

                    for row in reader:
                        value = row.get(date_field)
                        if not value:
                            raise RuntimeError(
                                f"{archive_path.name}:{member} 存在空的 {date_field}"
                            )
                        row_date = date.fromisoformat(value)
                        latest = row_date if latest is None else max(latest, row_date)

    if latest is None:
        raise RuntimeError(f"{directory} 中的历史 ZIP 没有数据行")

    return latest, int(archives[-1].stem) + 1


def validate_archive(
    archive_path: Path,
    code_field: str,
    date_field: str,
    start: date,
    end: date,
    expected_codes: set[str] | None = None,
) -> None:
    row_count = 0
    earliest: date | None = None
    latest: date | None = None
    codes: set[str] = set()

    with zipfile.ZipFile(archive_path) as archive:
        for member in csv_members(archive):
            with archive.open(member) as binary_file:
                text_file = io.TextIOWrapper(
                    binary_file,
                    encoding="utf-8-sig",
                    newline="",
                )
                reader = csv.DictReader(text_file)
                required_fields = {code_field, date_field}
                if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
                    raise RuntimeError(
                        f"{archive_path.name}:{member} 缺少 {code_field} 或 {date_field} 字段"
                    )

                for row in reader:
                    code = row.get(code_field)
                    value = row.get(date_field)
                    if not code or not value:
                        raise RuntimeError(
                            f"{archive_path.name}:{member} 存在空的代码或日期"
                        )
                    row_count += 1
                    codes.add(code.zfill(6))
                    row_date = date.fromisoformat(value)
                    earliest = row_date if earliest is None else min(earliest, row_date)
                    latest = row_date if latest is None else max(latest, row_date)

    if row_count == 0 or earliest is None or latest is None:
        raise RuntimeError(f"{archive_path.name} 没有数据行")
    if earliest < start or latest > end:
        raise RuntimeError(f"{archive_path.name} 中存在请求区间之外的数据")
    if latest != end:
        raise RuntimeError(
            f"{archive_path.name} 的最后日期是 {latest}，页面最新日期是 {end}"
        )
    if expected_codes is not None and codes != expected_codes:
        raise RuntimeError(
            f"{archive_path.name} 指数代码不符：实际 {sorted(codes)}，"
            f"预期 {sorted(expected_codes)}"
        )


class CsmarCrawler:
    def __init__(self, project_root: Path, username: str, password: str) -> None:
        self.project_root = project_root
        self.username = username
        self.password = password
        self.driver = self._build_driver()
        self.wait = WebDriverWait(
            self.driver,
            60,
            ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
        )
        self.query_handle = ""
        self.csmar_base_url = ""

    def _build_driver(self) -> webdriver.Chrome:
        options = Options()
        options.add_argument(
            f"--user-data-dir={self.project_root / 'state' / 'chrome_profile'}"
        )
        options.add_argument("--start-maximized")
        options.add_argument("--disable-background-mode")
        options.add_experimental_option(
            "prefs",
            {
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "profile.default_content_setting_values.automatic_downloads": 1,
            },
        )
        return webdriver.Chrome(
            service=Service(executable_path=str(cached_chromedriver())),
            options=options,
        )

    def close(self) -> None:
        self.driver.quit()

    def visible_elements(self, by: str, selector: str) -> list[WebElement]:
        return [
            element
            for element in self.driver.find_elements(by, selector)
            if element.is_displayed()
        ]

    def wait_visible(self, by: str, selector: str) -> WebElement:
        def find_unique(_: webdriver.Chrome) -> WebElement | bool:
            elements = self.visible_elements(by, selector)
            if len(elements) > 1:
                raise RuntimeError(f"选择器匹配到多个可见元素：{selector}")
            return elements[0] if elements else False

        return self.wait.until(find_unique)

    def wait_clickable(self, by: str, selector: str) -> WebElement:
        def find_unique(_: webdriver.Chrome) -> WebElement | bool:
            elements = [
                element
                for element in self.visible_elements(by, selector)
                if element.is_enabled()
            ]
            if len(elements) > 1:
                raise RuntimeError(f"选择器匹配到多个可点击元素：{selector}")
            return elements[0] if elements else False

        return self.wait.until(find_unique)

    def click(self, by: str, selector: str) -> WebElement:
        element = self.wait_clickable(by, selector)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            element,
        )
        element.click()
        return element

    def click_button(self, text: str) -> WebElement:
        return self.click(By.XPATH, f"//button[normalize-space(.)='{text}']")

    def login_webvpn(self) -> None:
        log("打开 WebVPN")
        self.driver.get("https://webvpn.swufe.edu.cn/")

        def login_state(_: webdriver.Chrome) -> str | bool:
            if self.visible_elements(By.XPATH, '//*[@id="__layout"]/div/div/div[2]/div/div/input'):
                return "portal"
            if self.visible_elements(By.ID, "username"):
                return "login"
            return False

        if self.wait.until(login_state) == "portal":
            return

        username_input = self.wait_clickable(By.ID, "username")
        password_input = self.wait_clickable(By.ID, "password")
        username_input.send_keys(self.username)
        password_input.send_keys(self.password)
        self.click(By.ID, "login_submit")

        def after_login(_: webdriver.Chrome) -> str | bool:
            if self.visible_elements(By.XPATH, '//*[@id="__layout"]/div/div/div[2]/div/div/input'):
                return "portal"
            if self.visible_elements(
                By.XPATH,
                "//*[self::a or self::button or self::input]"
                "[contains(normalize-space(.), '踢出以上会话')"
                " or contains(@value, '踢出以上会话')]",
            ):
                return "session_conflict"
            if self.visible_elements(By.ID, "captcha"):
                return "captcha"
            return False

        state = self.wait.until(after_login)
        if state == "captcha":
            raise RuntimeError("WebVPN 登录要求验证码，请先在浏览器配置中完成一次登录")
        if state == "session_conflict":
            self.click(
                By.XPATH,
                "//*[self::a or self::button or self::input]"
                "[contains(normalize-space(.), '踢出以上会话')"
                " or contains(@value, '踢出以上会话')]",
            )
            self.wait_visible(
                By.XPATH,
                '//*[@id="__layout"]/div/div/div[2]/div/div/input',
            )

    def open_csmar(self) -> None:
        log("从 WebVPN 打开 CSMAR")
        old_handles = set(self.driver.window_handles)
        search_input = self.wait_clickable(
            By.XPATH,
            '//*[@id="__layout"]/div/div/div[2]/div/div/input',
        )
        search_input.clear()
        search_input.send_keys("https://data.csmar.com/")
        search_input.send_keys(Keys.ENTER)

        def new_window(_: webdriver.Chrome) -> str | bool:
            handles = set(self.driver.window_handles) - old_handles
            if len(handles) > 1:
                raise RuntimeError("打开 CSMAR 时出现了多个新窗口")
            return next(iter(handles)) if handles else False

        self.query_handle = self.wait.until(new_window)
        self.driver.switch_to.window(self.query_handle)
        iframe = self.wait_visible(By.CSS_SELECTOR, "iframe[src*='csmar.html']")
        iframe_src = iframe.get_dom_attribute("src")
        if not iframe_src:
            raise RuntimeError("CSMAR iframe 缺少 src")

        proxy_url = self.driver.current_url.rstrip("/") + "/" + iframe_src.lstrip("/")
        self.driver.get(proxy_url)
        self.wait.until(lambda driver: driver.title == "CSMAR")
        self.wait.until(
            lambda driver: "西南财经大学本部"
            in driver.find_element(By.TAG_NAME, "body").text
        )
        self.csmar_base_url = self.driver.current_url.split("#", 1)[0]

    def open_table(self, route: str, dataset_name: str) -> date:
        self.driver.get(f"{self.csmar_base_url}#{route}")

        def table_state(driver: webdriver.Chrome) -> str | bool:
            body = driver.find_element(By.TAG_NAME, "body").text
            if f"{dataset_name}无权限" in body:
                return "forbidden"
            if dataset_name in body and "下载数据" in body:
                return "ready"
            return False

        if self.wait.until(table_state) == "forbidden":
            raise PermissionError(
                f"当前 CSMAR 账号没有“{dataset_name}”权限；页面操作项已被禁用"
            )

        body = self.driver.find_element(By.TAG_NAME, "body").text
        match = re.search(
            r"数据结束时间\s*[:：]?\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})",
            body,
        )
        if not match:
            raise RuntimeError(f"没有从“{dataset_name}”页面解析到数据结束时间")
        return date(*map(int, match.groups()))

    def select_all_a_shares(self) -> None:
        log("选择常用代码：全部A股")
        self.click(By.XPATH, "//label[normalize-space(.)='常用代码']")
        self.wait.until(
            lambda _: "is-checked"
            in self.driver.find_element(
                By.XPATH,
                "//label[normalize-space(.)='常用代码']",
            ).get_attribute("class")
        )
        selected = self.wait_visible(By.XPATH, "//input[@value='全部A股']")
        if selected.get_attribute("value") != "全部A股":
            raise RuntimeError("常用代码没有选中“全部A股”")

    def select_index_codes(self) -> None:
        expected_codes = {"000001", "000300", "000852", "000905"}
        log("选择指数代码：" + ", ".join(sorted(expected_codes)))
        self.click_button("代码选择")
        self.wait_visible(By.CSS_SELECTOR, ".el-dialog")

        for code in sorted(expected_codes):
            search_input = self.wait_clickable(
                By.CSS_SELECTOR,
                ".el-dialog input.el-input__inner:not([readonly])",
            )
            search_input.send_keys(Keys.CONTROL, "a")
            search_input.send_keys(Keys.BACKSPACE)
            search_input.send_keys(code)
            search_input.send_keys(Keys.ENTER)
            self.click(
                By.XPATH,
                "//div[contains(@class, 'el-dialog')]"
                "//div[contains(@class, 'wait-list-item') and contains(normalize-space(.), "
                f"'{code}')]//i[contains(@class, 'el-icon-circle-plus-outline')]",
            )
            self.wait.until(lambda _: code in self.selected_index_codes())

        actual_codes = self.selected_index_codes()
        if actual_codes != expected_codes:
            raise RuntimeError(
                f"指数代码选择不符：实际 {sorted(actual_codes)}，"
                f"预期 {sorted(expected_codes)}"
            )
        self.click(
            By.XPATH,
            "//div[contains(@class, 'el-dialog')]//button[normalize-space(.)='确定']",
        )
        self.wait.until(lambda _: not self.visible_elements(By.CSS_SELECTOR, ".el-dialog"))

    def selected_index_codes(self) -> set[str]:
        selected = self.visible_elements(By.CSS_SELECTOR, ".el-dialog .select-list.last")
        if len(selected) != 1:
            raise RuntimeError("指数代码选择窗口中没有唯一的已选列表")
        return set(re.findall(r"\b\d{6}\b", selected[0].text))

    def select_all_fields(self, expected_count: int) -> None:
        log("选择全部字段")
        self.click_button("全选")
        self.wait.until(
            lambda driver: f"已选：{expected_count}/{expected_count}"
            in driver.find_element(By.TAG_NAME, "body").text
        )

    def select_csv_format(self) -> None:
        log("选择 CSV 格式")
        selector = (
            "//label[contains(@class, 'el-radio')"
            " and contains(normalize-space(.), 'CSV格式')"
            " and contains(normalize-space(.), '*.csv')"
            " and not(contains(normalize-space(.), 'Matlab'))]"
        )
        self.click(By.XPATH, selector)
        self.wait.until(
            lambda _: "is-checked"
            in self.driver.find_element(By.XPATH, selector).get_attribute("class")
            or bool(
                self.driver.find_element(By.XPATH, selector).find_elements(
                    By.CSS_SELECTOR,
                    "input:checked",
                )
            )
        )

    def set_date_range(self, start: date, end: date) -> None:
        def date_inputs(_: webdriver.Chrome) -> list[WebElement] | bool:
            inputs = self.visible_elements(
                By.CSS_SELECTOR,
                ".el-date-editor input.el-input__inner",
            )
            if len(inputs) > 2:
                raise RuntimeError(f"日期输入框数量应为 2，实际为 {len(inputs)}")
            return inputs if len(inputs) == 2 else False

        inputs = self.wait.until(date_inputs)

        for element, value in zip(inputs, (start.isoformat(), end.isoformat()), strict=True):
            self.driver.execute_script(
                """
                const input = arguments[0];
                const value = arguments[1];
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype,
                    "value"
                ).set;
                input.removeAttribute("readonly");
                setter.call(input, value);
                input.dispatchEvent(new Event("input", {bubbles: true}));
                input.dispatchEvent(new Event("change", {bubbles: true}));
                """,
                element,
                value,
            )
            element.send_keys(Keys.TAB)
            self.wait.until(lambda _, item=element, expected=value: item.get_attribute("value") == expected)

    def set_download_directory(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.driver.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(directory)},
        )

    def download_range(
        self,
        directory: Path,
        index: int,
        start: date,
        end: date,
    ) -> Path:
        self.set_date_range(start, end)
        self.set_download_directory(directory)

        partials = list(directory.glob("*.crdownload"))
        if partials:
            raise RuntimeError("下载目录中存在未完成文件：" + ", ".join(p.name for p in partials))

        before_files = {path.name for path in directory.iterdir() if path.is_file()}
        old_handles = set(self.driver.window_handles)
        log(f"下载 {start} 至 {end}")
        self.click_button("下载数据")

        def result_window(_: webdriver.Chrome) -> str | bool:
            handles = set(self.driver.window_handles) - old_handles
            if len(handles) > 1:
                raise RuntimeError("下载时出现了多个结果窗口")
            if not handles:
                return False
            handle = next(iter(handles))
            self.driver.switch_to.window(handle)
            return handle if "sdownload.html" in self.driver.current_url else False

        WebDriverWait(self.driver, 1800).until(result_window)
        self.click(
            By.XPATH,
            "//a[contains(translate(@href, 'ZIP', 'zip'), '.zip')"
            " or contains(translate(normalize-space(.), 'ZIP', 'zip'), '.zip')]",
        )

        def completed_download(_: webdriver.Chrome) -> Path | bool:
            if list(directory.glob("*.crdownload")):
                return False
            new_files = [
                path
                for path in directory.iterdir()
                if path.is_file()
                and path.name not in before_files
                and path.suffix.lower() == ".zip"
            ]
            if len(new_files) > 1:
                raise RuntimeError("一次下载产生了多个 ZIP 文件")
            if not new_files:
                return False
            return new_files[0] if zipfile.is_zipfile(new_files[0]) else False

        downloaded = WebDriverWait(self.driver, 1800).until(completed_download)
        target = directory / f"{index}.zip"
        if target.exists():
            raise FileExistsError(f"目标文件已存在：{target}")
        downloaded.rename(target)

        self.driver.close()
        self.driver.switch_to.window(self.query_handle)
        return target

    def update_stocks(self) -> None:
        log("准备更新日个股回报率")
        latest_online = self.open_table(
            "/datacenter/singletable/search?databaseId=63&tbId=4",
            "日个股回报率文件",
        )
        self.select_all_a_shares()
        self.select_all_fields(24)
        self.select_csv_format()

        directory = self.project_root / "raw" / "stocks"
        latest_local, next_index = latest_local_date(directory, "Trddt")
        if latest_local >= latest_online:
            log(f"个股数据已是最新日期：{latest_local}")
            return

        ranges = split_date_range(latest_local + timedelta(days=1), latest_online, 5)
        for offset, (start, end) in enumerate(ranges):
            archive = self.download_range(directory, next_index + offset, start, end)
            validate_archive(archive, "Stkcd", "Trddt", start, end)
            log(f"个股文件校验通过：{archive.name}")

    def update_indexes(self) -> None:
        log("准备更新国内指数日行情")
        latest_online = self.open_table(
            "/datacenter/singletable/search?databaseId=42&tbId=45",
            "国内指数日行情文件",
        )
        self.select_index_codes()
        self.select_all_fields(10)
        self.select_csv_format()

        directory = self.project_root / "raw" / "indexes"
        latest_local, next_index = latest_local_date(directory, "Idxtrd01")
        if latest_local >= latest_online:
            log(f"指数数据已是最新日期：{latest_local}")
            return

        expected_codes = {"000001", "000300", "000852", "000905"}
        ranges = split_date_range(latest_local + timedelta(days=1), latest_online, 4)
        for offset, (start, end) in enumerate(ranges):
            archive = self.download_range(directory, next_index + offset, start, end)
            validate_archive(
                archive,
                "Indexcd",
                "Idxtrd01",
                start,
                end,
                expected_codes,
            )
            log(f"指数文件校验通过：{archive.name}")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env", override=True)
    username = os.getenv("WEBVPN_USERNAME")
    password = os.getenv("WEBVPN_PASSWORD")
    if not username or not password:
        raise RuntimeError(".env 中缺少 WEBVPN_USERNAME 或 WEBVPN_PASSWORD")

    log("启动 Chrome")
    crawler = CsmarCrawler(project_root, username, password)
    try:
        crawler.login_webvpn()
        crawler.open_csmar()
        crawler.update_stocks()
        crawler.update_indexes()
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
