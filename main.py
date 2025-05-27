import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

OPEN_BROWSER = True
SAVING_INTERVAL_SECONDS = 5
SAVING_PATH = Path(__file__).parent.resolve() / "scraped.json"
load_dotenv("./.env")
NEEDED_ENV_KEYS = [
    "discord_email",
    "discord_pass",
    "target_server_name",
    "target_channel_id",
]
for key in NEEDED_ENV_KEYS:
    if not os.getenv(key):
        raise ValueError(f"INVALID OR MISSING .env KEY OR FILE: {key}")


@dataclass
class Message:
    author_name: str | None
    author_id: str | None
    body: str | None
    time: str | None
    server_name: str | None
    channel_id: str | None

    def to_dict(self) -> dict[str, str | None | bool]:
        return {
            "author_name": self.author_name,
            "author_id": self.author_id,
            "body": self.body,
            "time": self.time,
        }


class DiscordSession:
    def __init__(self, sel: tuple[WebDriver, Options]) -> None:
        self.sel = sel

    def __enter__(self) -> None:
        self.email, self.passkeys = self.get_keys()
        self.driver, self.options = self.sel
        self.utils = Helpers(self.driver)
        self.init_stealth()
        self.enter_discord()

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        if exc_type:
            self.utils.screenshot()
        self.driver.quit()

    def get_keys(self) -> tuple[str, str]:
        email = os.getenv("discord_email")
        keys = os.getenv("discord_pass")
        if not email or not keys:
            sys.exit(1)
        return email, keys

    def init_stealth(self) -> None:
        return stealth(
            self.driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    def enter_discord(self) -> None:
        util = self.utils
        self.driver.get("https://discord.com/login")

        email_field = util.wait_aria("Email or Phone Number")
        email_field.click()
        email_field.send_keys(self.email)

        passwd_field = util.wait_aria("Password")
        passwd_field.click()
        passwd_field.send_keys(self.passkeys)

        login_button = util.wait_css('type="submit"')
        login_button.click()


class MessageScrape:
    def __init__(self, driver: WebDriver) -> None:
        self.server = None
        self.driver = driver
        self.utils = Helpers(driver)
        self.enter_server()
        time.sleep(0.05)
        self.driver.get(
            f"https://discord.com/channels/{self.get_server_id()}/{os.getenv('target_channel_id')}"
        )
        self.logged = self.scrape_messages()

    def get_server_id(self) -> str:
        return self.driver.current_url.rstrip("/").split("/")[-2]

    def enter_server(self) -> None:
        server_div = self.utils.wait_aria("Servers")
        time.sleep(0.25)
        servers = server_div.find_elements(By.XPATH, './/*[@tabindex="-1"]')
        if servers:
            print("FOUND SERVERS.")
            target = os.getenv("target_server_name").lower()  # type: ignore
            found_target = None
            for server in servers:
                name = server.find_element(By.XPATH, ".//span").text.lower()
                found_target = (name, server) if name == target else found_target
                print(f"FOUND SERVER: {name}, IS TARGET: {name == target}")

            if found_target:
                print(f"ENTERING SERVER: {found_target[0]}")
                self.server = found_target[0]
                found_target[1].click()

            else:
                print("TARGET SERVER NOT FOUND. EXITING...")
                sys.exit(1)

        else:
            print("NO SERVERS FOUND IN DISCORD. EXITING...")
            sys.exit(1)

    def find_id(self, msg: WebElement) -> str | None:
        try:
            u_id = msg.find_element(
                By.XPATH, './/span[contains(@id, "message-username-")]'
            ).get_attribute("id")
            if u_id:
                return u_id.rsplit("-", 1)[-1]
        except NoSuchElementException:
            print("COULD NOT GET ID FROM A MESSAGE.")

    def find_name(self, msg: WebElement) -> str | None:
        try:
            return msg.find_element(
                By.XPATH,
                './/span[contains(@class, "username_") and @role="button" and text()]',
            ).text
        except NoSuchElementException:
            print("COULD NOT GET USERNAME FROM A MESSAGE.")

    def find_text(self, msg: WebElement) -> str | None:
        try:
            wrapper = msg.find_element(
                By.XPATH, './/div[contains(@id, "message-content")]'
            )
            result = ""
            elements = wrapper.find_elements(
                By.XPATH, ".//*[string-length(text()) > 0 or self::br]"
            )
            for elm in elements:
                if elm.tag_name == "br":
                    result += "\n"
                else:
                    result += elm.text.removeprefix('"').removesuffix('"')
            return result
        except NoSuchElementException:
            print("COULD NOT GET BODY FROM A MESSAGE.")

    def find_time(self, msg: WebElement) -> str | None:
        try:
            return msg.find_element(
                By.XPATH,
                ".//time[@datetime]",
            ).get_attribute("datetime")
        except NoSuchElementException:
            print("COULD NOT GET DATETIME FROM A MESSAGE.")

    def scrape_messages(self) -> list[Message]:
        message_box = self.utils.wait_css('data-list-id="chat-messages"')
        time.sleep(1)
        for _ in range(10):
            message_box.send_keys(webdriver.Keys.END)
            time.sleep(0.2)  # make sure to REALLY scroll down.
        ids = []
        logged_messages = []
        print(
            "BEGGING TO SCRAPE. TO EXIT, PRESS CTRL+C. "
            "BE CAREFUL NOT TO PRESS IT TWICE!"
        )
        while True:
            try:
                current_messages = message_box.find_elements(
                    By.XPATH, './/li[contains(@class, "messageListItem")]'
                )
                for msg in current_messages:
                    try:
                        m_id = msg.get_attribute("id")
                    except StaleElementReferenceException:
                        print("ERROR: FAILED TO GET ID FROM A MESSAGE.")
                        continue
                    if m_id in ids:
                        continue
                    ids.append(m_id)
                    author_name = self.find_name(msg)
                    print(f"READ MESSAGE BY {author_name}.")
                    if author_name:
                        if author_name.startswith("@"):
                            continue  # message is the preview of the message of someone being replied to
                    logged_messages.append(
                        Message(
                            author_name=author_name,
                            author_id=self.find_id(msg),
                            body=self.find_text(msg),
                            time=self.find_time(msg),
                            server_name=self.server,
                            channel_id=os.getenv("target_channel_id"),
                        )
                    )
                self.save_logs(logged_messages)
                logged_messages = []
                time.sleep(SAVING_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                break
        return logged_messages

    def save_logs(self, to_save: list[Message]) -> None:
        file = SAVING_PATH
        old: list[dict] = []
        if file.exists():
            text = file.read_text("utf-8")
            if len(text) > 3:
                error = False
                try:
                    old = json.loads(text)
                    if not isinstance(old, list):
                        error = True
                except json.decoder.JSONDecodeError:
                    error = True
                if error:
                    print(f"ERROR: INVALID {file.name} FILE. PARSING ERROR. RENAMING...")
                    file.rename(Path(__file__).parent / f"invalidJSON-{time.time()}.json")
        old.extend(map(lambda m: m.to_dict(), to_save))
        seen = set()
        unique_logs = []
        for entry in old:
            key = (entry.get("author_id"), entry.get("time"))
            if key not in seen:
                seen.add(key)
                unique_logs.append(entry)
        file.write_text(json.dumps(unique_logs), "utf-8")


class Helpers:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self.waiter = WebDriverWait(self.driver, 10)

    def wait_aria(self, aria: str) -> WebElement:
        return self.wait_css(f'aria-label="{aria}"')

    def wait_css(self, css_selector: str) -> WebElement:
        return self.wait_any(By.CSS_SELECTOR, f"[{css_selector}]")

    def wait_any(self, by: str, select: str) -> WebElement:
        return self.waiter.until(EC.visibility_of_element_located((by, select)))

    @staticmethod
    def init_sel() -> tuple[WebDriver, Options]:
        options = webdriver.ChromeOptions()
        if not OPEN_BROWSER:
            options.add_argument("--headless")
        options.add_argument("start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(options)
        return driver, options

    def screenshot(self) -> None:
        original_size = self.driver.get_window_size()
        full_width = self.driver.execute_script(
            "return document.body.parentNode.scrollWidth"
        )
        full_height = self.driver.execute_script(
            "return document.body.parentNode.scrollHeight"
        )
        self.driver.set_window_size(full_width, full_height)
        self.driver.save_screenshot("screenshot.png")
        self.driver.set_window_size(original_size["width"], original_size["height"])


if __name__ == "__main__":
    sel = Helpers.init_sel()
    with DiscordSession(sel):
        print("SUCCESSFULLY LOGGED ON.")
        MessageScrape(sel[0])
        print("FINISHED SCRAPING. CLOSING BROWSER...")
    print("PROGRAM FINISHED RUNNING.")
