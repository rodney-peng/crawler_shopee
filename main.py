import os
import sys
import pickle
import logging
import datetime
import inspect
from env import *
from time import gmtime, strftime,sleep
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class Config:

    DEBUG = False
    LOGGING_PATH = 'log'
    WAIT_TIMEOUT = 5
    elements_by_css = {
        "POP_MODAL": ".shopee-popup__close-btn",
        "AVATAR": ".shopee-avatar",
        "NAV_LOGIN_MODAL": ".navbar__link--account",
        "LOGIN_SUBMIT": "#modal > aside > div > div > div > div > div > div > button:nth-child(2)",
        "SMS_MODAL": ".shopee-authen__outline-button",
        "SMS_TEXT": ".shopee-authen .input-with-status__input",
        "SMS_SUBMIT": ".shopee-authen .btn-solid-primary",
        "LOGIN_FAILED": ".shopee-authen .shopee-authen__error",
        "COIN_PAGE_READY": ".check-box",
        "COIN_NOW": ".check-box .total-coins",
        "GET_COIN": ".check-box .check-in-tip",
        "COIN_REGULAR": ".check-box .top-btn.Regular",
        "COIN_VALUE": "._37aS8q",
        "COIN_BUTTON": "._1Puh5H"
    }
    elements_by_name = {
        "LOGIN_USER": "loginKey",
        "LOGIN_PASS": "password"
    }
    urls = {
        "INDEX": "https://shopee.tw",
        "COIN_PAGE": "https://shopee.tw/shopee-coins"
    }
    path = os.path.dirname(os.path.abspath(__file__))


class Logger(Config):
    def __init__(self):
        path = os.path.join(self.path, self.LOGGING_PATH)
        path = "{}/{}".format(path, datetime.datetime.now().strftime("shopee.%Y-%m.log"))
#        if not os.path.exists(path):
#            os.makedirs(path)
        logging_level = logging.DEBUG if self.DEBUG else logging.INFO
        logger = logging.getLogger()
        logger.setLevel(logging_level)
        formatter = logging.Formatter('[%(filename)s:%(lineno)s - %(funcName)20s() ] %(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        fh = logging.FileHandler(path)
        fh.setFormatter(formatter)
        logger.addHandler(ch)
        logger.addHandler(fh)
        self.logger = logger

    def get_logger(self):
        return self.logger


logger = Logger().get_logger()

class Driver(Config):

    def __init__(self, width, height):

        chrome_options = Options()
        # Hide the chromedriver
        if not self.DEBUG or self.path == '/code':
#            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('disable-infobars')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome('chromedriver',options=chrome_options)
        self.driver.set_window_size(width, height)
        self.path = os.path.dirname(os.path.abspath(__file__))
        print("Init driver done.")

    def saveCookie(self, cookieName):
        with open(self.path + '/' + cookieName, 'wb') as filehandler:
            pickle.dump(self.driver.get_cookies(), filehandler)
        logger.info("Save cookie to {}".format(cookieName))

    def loadCookie(self, cookieName):
        with open(self.path + '/' + cookieName, 'rb') as cookiesfile:
            for cookie in pickle.load(cookiesfile):
                self.driver.add_cookie(cookie)

    def getRequest(self, url):
        self.driver.get(self.urls.get(url))

    def wait_until(self, method=None, target=None):
        if method == 'css':
            selector = By.CSS_SELECTOR
            target = self.elements_by_css.get(target)

        try:
            element = WebDriverWait(self.driver, self.WAIT_TIMEOUT).until(
                EC.presence_of_element_located((selector, target))
            )
            if isinstance(element, webdriver.remote.webelement.WebElement):
                logger.info( "Found <{} \"{}\">{}</>".format(element.tag_name, target, element.text) )
                return element

        except Exception as e:
            logger.error(repr(e))

        return False

    def find(self, method=None, target=None):
        try:
            if method == 'css':
                target = self.elements_by_css.get(target)
                result = self.driver.find_elements_by_css_selector(target)
            if method == 'name':
                target = self.elements_by_name.get(target)
                result = self.driver.find_elements_by_name(target)

            if (len(result) is 1) and isinstance(result[0], webdriver.remote.webelement.WebElement):
                logger.info( "Found <{} \"{}\">{}</>".format(result[0].tag_name, target, result[0].text) )
                return result[0]

        except Exception as e:
            logger.error(repr(e))

        return False

def has_substr( string, substring ):
    ''' str.find() doesn't work, convert to byte data and use keyword 'in'
    if coin_button.text.find('登入'): True
    if coin_button.text.find('領取'): True
    if coin_button.text.find('簽到'): True
    '''
    return substring.encode('utf-8') in string.encode('utf-8')

class Crawler(Driver, Config):

    def __init__(self):
        super().__init__(1200, 800)

    def checkPopModal(self):
        try:
            sleep(3)
            pop = self.find("css", "POP_MODAL")
            pop.click()
            logger.info("pop modal close")
        except Exception as e:
            logger.info("pop modal not found: " + repr(e))

    def checkLogin(self):
        return bool(self.wait_until("css", "AVATAR"))

    def loginByCookie(self, cookieName):
        try:
            self.loadCookie(cookieName)
            self.driver.refresh()
            logger.info("Use {} to login".format(cookieName))
        except Exception as e:
            logger.info("{} not found".format(cookieName))

    def loginByPass(self):
        try:
            # click to show login modal
            login_button = self.find("css", "NAV_LOGIN_MODAL")[1]
            login_button.click()
            self.wait_until("css", "LOGIN_SUBMIT")
        except Exception as e:
            logger.error("Login Modal not showing: "+repr(e))
            self.close()
        try:
            # Enter Account & Password
            accountText = self.find("name", "LOGIN_USER")
            passwordText = self.find("name", "LOGIN_PASS")
            submitButtom = self.find("css", "LOGIN_SUBMIT")

            accountText.send_keys(text_username)
            passwordText.send_keys(text_password)
            submitButtom.click()
            logger.info("Use password to login")
        except Exception as e:
            logger.error("Wrong account and password: "+repr(e))
            self.close()

    def login(self):
        ''' login manually or by cookie
        '''
        self.getRequest("COIN_PAGE")
        coin_button = self.wait_until("css", "COIN_BUTTON")
        if not coin_button:
            logger.info("Page loading error!")
            return False
        if has_substr(coin_button.text, '登入'):
            self.loginByCookie(cookie_name)
            if not self.checkLogin():
                coin_button.click()
                input('Please login before proceed! Press <enter> to continue!')
            else:
                logger.info( "Login by cookie!" )
        if self.checkLogin():
            logger.info("Login successful!")
            self.saveCookie(cookie_name)
        else:
            logger.info("Cannot login!")
            return False
        return True

    def checkSMS(self):
        try:
            # Check SMS textbox exists
            self.wait_until("css", "SMS_MODAL")
            # Catch text & submit buttom
            smsText = self.find("css", "SMS_TEXT")
            smsSubmit = self.find("css", "SMS_SUBMIT")

            text_sms = input("Please Enter SMS code in 60 seconds: ")
            smsText.clear()
            smsText.send_keys(text_sms)
            smsSubmit.click()
            # handle sms error
            try:
                # wait to check if login success
                self.wait_until("css", "AVATAR")
            except:
                #login failed
                smsError = self.find("css", "LOGIN_FAILED")
                if len(smsError) > 0:
                    logger.error("Sending SMS code "+smsError[0].text)
                else:
                    logger.error("Sending SMS code Run time out.")
                self.close()
                sys.exit(0)
        except Exception as e:
            logger.info("No need SMS authenticate: "+repr(e))

    def clickCoin(self):
        try:
            # wait for page loading
            self.getRequest("COIN_PAGE")
            self.wait_until("css", "COIN_PAGE_READY")
            try:
                self.wait_until("css", "GET_COIN")
                # get information
                current_coin = self.find("css", "COIN_NOW")
                get_coin = self.find("css", "GET_COIN")
                #show before information
                logger.info("目前有：" + current_coin.text + " 蝦幣，" + get_coin.text)
                #click to get shopee coin
                get_coin.click()
            except:
                # Already click
                logger.info("今天已經獲取過蝦幣")
            #wait for already information display login-check-btn
            self.wait_until("css", "COIN_REGULAR")
            #show after information
            current_coin = self.find("css", "COIN_NOW")
            coin_regular = self.find("css", "COIN_REGULAR")
            logger.info("目前有：" + current_coin.text + " 蝦幣，" + coin_regular.text)
        except Exception as e:
            logger.error(repr(e))
            self.close()

    def claimCoin(self):
        if not self.login():
            self.driver.close()
            return False
        coin_button = self.wait_until("css", "COIN_BUTTON")
        if coin_button:
            if has_substr(coin_button.text, '簽到'):
                logger.info( "Claiming coin for today..." )
                coin_button.click()
                coin_button = self.wait_until("css", "COIN_BUTTON")
        else:
            logger.info("Coin button not found!")
            self.driver.close()
            return False
        coin_value = self.find("css", "COIN_VALUE")
        if coin_value:
            last_value = ''
            # wait while the coin value counting
            while coin_value.text != last_value:
                last_value = coin_value.text
                sleep(1)
            logger.info("目前有 " + coin_value.text + " 蝦幣, " + coin_button.text)
        else:
            logger.info("Coin value not found!")
            self.driver.close()
            return False
        self.driver.close()
        return True

    def run(self):
        self.getRequest("INDEX")
        self.checkPopModal()
        #Use cookie to login
        self.loginByCookie(cookie_name)
        if not self.checkLogin():
            #Use pass to login
            self.loginByPass()
            if not self.checkLogin():
                self.checkSMS()
                if not self.checkLogin():
                    #Login failed
                    self.close()
        #After login, Go to coin page
        self.saveCookie(cookie_name)
        self.clickCoin()
        self.close()

    def close(self):
        self.driver.close()
        logger.info("Program exit")
        sys.exit(0)


if __name__ == "__main__":
    Crawler().claimCoin()

