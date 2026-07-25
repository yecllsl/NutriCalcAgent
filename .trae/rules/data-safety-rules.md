# 数据安全规则

1. 所有饮食记录、用户档案、评估报告仅存储在本地 data/ 目录，禁止上传到任何外部服务
2. 食物图片存储在项目目录下的 data/food_images/，不外传
3. 导出数据前需用户确认（export_data 返回 needs_confirmation=True）
4. 不记录用户姓名等个人身份信息，user_id 默认为 "default"
5. OCR 使用本地 PaddleOCR 部署，不调用外部 OCR API
6. Web 服务绑定 127.0.0.1，仅本机访问
7. 营养师建议 prompt 在本地构造，由 MCP 宿主 LLM 执行，不直接外传饮食数据
