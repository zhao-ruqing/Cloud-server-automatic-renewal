# -*- coding: utf-8 -*-
"""Page selectors. Chinese UI text is Unicode-escaped so source stays ASCII."""

# Shared Sanfeng / Abeiyun console
CLOUD = {
    "login_btn": "#loginSubmit",
    "username": "#userName",
    "password": "#passwordInput",
    "nav_extend_btn": 'button.el-button--primary:has-text("\u514d\u8d39\u5ef6\u671f")',
    "extend_tab": "#tab-seven",
    "url_input": 'input[placeholder="\u8bf7\u8f93\u5165\u53d1\u5e16\u7f51\u5740http://"]',
    "file_input": "#fileImg1",
    "submit_btn": 'button.el-button--primary:has-text("\u63d0\u4ea4")',
    "expiry_label": "\u5230\u671f\u65f6\u95f4",
}

SANFENG = CLOUD
ABEIYUN = CLOUD

CNBLOGS = {
    "login_url_contains": "account.cnblogs.com/signin",
    "username": 'input[formcontrolname="username"]',
    "password": 'input[formcontrolname="password"]',
    "login_btn": 'button.action-button:has-text("\u767b\u5f55")',
    "title_input": "#post-title",
    "body_editor": "#md-editor",
    "publish_checkbox": "#isPublished",
    "publish_btn": '[data-el-locator="publishBtn"]',
    "saved_page": '[data-el-locator="post-saved-page"]',
    "saved_title_link": "a.link-post-title",
    "saved_view_link": 'a:has-text("\u7acb\u5373\u67e5\u770b")',
    "article_title": "#cb_post_title_url, h1.postTitle, .postTitle",
    "article_body": "#cnblogs_post_body",
}

ZHIHU = {
    "title_input": 'textarea[placeholder*="\u8bf7\u8f93\u5165\u6807\u9898"]',
    "body_editor": '.public-DraftEditor-content[contenteditable="true"]',
    "add_topic_btn": 'button:has-text("\u6dfb\u52a0\u8bdd\u9898")',
    "topic_search": 'input[aria-label="\u641c\u7d22\u8bdd\u9898"]',
    "publish_btn": 'button.Button--primary:has-text("\u53d1\u5e03")',
    "login_text": "\u767b\u5f55\u77e5\u4e4e",
    "review_text": "\u5ba1\u6838",
    "qr_container": ".Qrcode-container",
    "qr_image": ".Qrcode-qrcode",
    "captcha": ".yidun, .geetest_holder, iframe[src*='captcha']",
}
