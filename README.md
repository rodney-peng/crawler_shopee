# Shopee coin getter
![CI status](https://img.shields.io/badge/build-passing-brightgreen.svg)

Shopee coin getter is a script to collect daily shopee coins.

![alt text](https://raw.githubusercontent.com/rodney-peng/crawler_shopee/master/readme/overall-1.png)
## Dependencies

    python>=3.6
    selenium>=3.13.0

## Usage

clone the repository,
copy env.py.sample to env.py and optionally edit the cookie name in env.py:

    cookie_name = "cookie.pkl"

Please note that text_username and text_password are no longer used and kept only for compatibility.

Then run:

    python main.py

## License

[MIT](https://choosealicense.com/licenses/mit/)
