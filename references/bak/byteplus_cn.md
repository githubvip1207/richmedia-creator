# BytePlus / ModelArk：独立供应商

核验日期：2026-10-21。供应商 ID 为 `byteplus`，国内供应商 ID 仍为 `volcengine`。不要将二者当作同一账户的不同区域。模型目录、价格快照、认证、任务 ID 和素材 ID 均独立。相似的传输格式允许共享请求序列化逻辑，但不意味着可以回退使用另一家的凭证，或跨账户信任素材。

| 设置 | Volcengine | BytePlus |
|---|---|---|
| 项目 .env 配置项 | VOLCENGINE_API_KEY | BYTEPLUS_API_KEY |
| API 基础地址 | https://ark.cn-beijing.volces.com/api/v3 | https://ark.ap-southeast.bytepluses.com/api/v3 |
| 计费币种 | CNY | USD |
| 模型目录 | models/volcengine.json | models/byteplus.json |

BytePlus 模型别名分别解析为 `dreamina-seedance-2-5-260628`、`dreamina-seedance-2-0-260128`、`dreamina-seedance-2-0-fast-260128`、`dreamina-seedance-2-0-mini-260615`、`dola-seedream-5-0-pro-260628` 和 `dola-seedream-5-0-flash-260915`。准确 ID 和模型限制维护在其目录中。它支持国内适配器已实现的同一组标准图片和视频操作。公共校验规则已经对照 BytePlus API 参考核验；后续模型变化必须独立核验。

BytePlus 在自己的基础地址下使用 `/images/generations`、`/contents/generations/tasks`、`/contents/generations/tasks/{id}`。生成和编辑采用低成本 480p、最短时长默认值，并要求任务确认。2.5 编辑使用 ratio=adaptive、duration=-1；首帧、首尾帧、延长也锁定为自适应比例。Pro/Flash 支持单张图片输出、多参考图编辑、局部编辑和图层拆分；普通原生组图、流式输出、搜索仍不支持。本地图片和音频以 Base64 发送；API 允许时，远程 HTTPS URL 与已有 BytePlus `asset://` ID 直接传递。视频输入接受 HTTPS URL 或已有素材 ID，不接受 Base64。本技能不调用 BytePlus 上传 API，也不创建素材 ID；用户必须另行通过 BytePlus 或获准存储上传，再提供该供应商的素材 ID 或 URL。凭证只发送到所选适配器的固定 HTTPS API 主机，并禁用携带凭证的重定向。

本技能从项目 `.env` 读取 `BYTEPLUS_API_KEY`，与 Volcengine 的 `VOLCENGINE_API_KEY` 独立。应单独配置 BytePlus API Key、余额和模型开通状态；存在密钥不代表账户资格、访问权限、速率配额或真实生成成功已验证。本技能不创建账户、不充值、不购买套餐，也不复用国内余额。

`asset://` ID 必须包含与目标供应商匹配的 `provenance.provider`。分别确认各供应商与账户的素材、人像信任资格。不要把国内素材 ID 提交至 BytePlus，也不要假定 Ark 可信真人像在海外同样可信。通用公开产品参考只有在适用且已获授权时才能复用；每份报价都会展示实际传输的素材。

## 官方来源

- [快速开始与密钥/API 用法](https://docs.byteplus.com/en/docs/modelark/quick-start)
- [模型列表](https://docs.byteplus.com/en/docs/modelark/model-list)
- [价格、公式与最低 Token 规则](https://docs.byteplus.com/en/docs/modelark/model-pricing)
- [创建视频任务 API](https://docs.byteplus.com/en/docs/modelark/create-video-generation-task-api)
- [查询视频任务 API](https://docs.byteplus.com/en/docs/modelark/get-video-generation-task-api)
- [视频教程与像素映射](https://docs.byteplus.com/en/docs/modelark/video-generation-tutorial)
- [图片 API](https://docs.byteplus.com/en/docs/modelark/image-generation-api)
- [Seedream Pro/Flash 教程](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro)
