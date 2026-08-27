"""页面选择器集中管理。"""

ZHIHU = {
    "title_input": 'textarea[placeholder*="请输入标题"]',
    "body_editor": '.public-DraftEditor-content[contenteditable="true"]',
    "add_topic_btn": 'button:has-text("添加话题")',
    "topic_search": 'input[aria-label="搜索话题"]',
    "publish_btn": 'button.Button--primary:has-text("发布")',
}

SANFENG = {
    "login_btn": "#loginSubmit",
    "username": "#userName",
    "password": "#passwordInput",
    "file_input": "",
    "url_input": "",
    "submit_btn": "",
    "success_indicator": "",
}

ABEIYUN = {
    "login_btn": "#loginSubmit",
    "username": "#userName",
    "password": "#passwordInput",
    # 服务器详情导航页顶部「免费延期」按钮（点击后进入续期表单）
    "nav_extend_btn": 'button.el-button--primary:has-text("免费延期")',
    "extend_tab": "#tab-seven",
    "url_input": 'input[placeholder="请输入发帖网址http://"]',
    "file_input": "#fileImg1",
    "submit_btn": 'button.el-button--primary:has-text("提交")',
}
