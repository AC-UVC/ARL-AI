"""ARL MCP Server —— 把 ARL（资产侦察灯塔）暴露为 MCP 工具给 AI 使用。

安全约束（本包的最高优先级设计）：
1. 所有文件增删改查只允许发生在工作目录（ARL_MCP_WORKSPACE，默认为启动目录）内；
2. 所有临时文件只允许写在工作目录的 .tmp 子目录下；
3. 工具参数里的 URL 出网前必须通过 SSRF 防护校验（仅 http/https，
   拒绝 localhost/环回/私有/保留地址）。
"""

__version__ = "1.0.0"
