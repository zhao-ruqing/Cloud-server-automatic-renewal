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
    # 二期：续期页 SPA 选择器待补充
    "file_input": "",
    "url_input": "",
    "submit_btn": "",
    "success_indicator": "",
}
