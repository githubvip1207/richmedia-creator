# BytePlus / ModelArk — separate supplier

Verified 2026-10-21. Supplier ID is `byteplus`; domestic supplier ID remains `volcengine`. Do not treat them as regions of one account. Model catalogs, pricing snapshots, authentication, task IDs and asset IDs are independent. Similar wire formats permit shared request serialization; this does not authorize credential fallback or cross-account asset trust.

| Setting | Volcengine | BytePlus |
|---|---|---|
| Project .env setting | VOLCENGINE_API_KEY | BYTEPLUS_API_KEY |
| API base | https://ark.cn-beijing.volces.com/api/v3 | https://ark.ap-southeast.bytepluses.com/api/v3 |
| Billing currency | CNY | USD |
| Model catalog | models/volcengine.json | models/byteplus.json |

BytePlus aliases resolve to `dreamina-seedance-2-5-260628`, `dreamina-seedance-2-0-260128`, `dreamina-seedance-2-0-fast-260128`, `dreamina-seedance-2-0-mini-260615`, `dola-seedream-5-0-pro-260628` and `dola-seedream-5-0-flash-260915`. Exact IDs and model limits are maintained in its catalog. It supports the same implemented standard image/video operations as the domestic adapter. The common validation rules were checked against the BytePlus API references; future model changes must be verified independently.

BytePlus uses `/images/generations`, `/contents/generations/tasks` and `/contents/generations/tasks/{id}` under its own base URL. Creation and edits use the low-cost 480p/minimum-duration defaults and require the task confirmation. 2.5 editing uses ratio=adaptive and duration=-1; first-frame/first-last-frame/extension also lock adaptive ratio. Pro/Flash supports single-image output, multi-reference image editing, region edits and layer decomposition; ordinary native image-group/stream/search remain unsupported. Local image/audio inputs are sent as Base64; remote HTTPS URLs and existing BytePlus `asset://` IDs are passed through where the API allows them. Video inputs accept HTTPS URL or an existing asset ID, not Base64. The skill does not call BytePlus upload APIs or create asset IDs; users must upload through BytePlus or approved storage separately, then provide the resulting supplier asset ID or URL. Credentials are sent only to the selected adapter's fixed HTTPS API host, with credential redirects disabled.

The skill reads `BYTEPLUS_API_KEY` from project `.env`, independently of Volcengine's `VOLCENGINE_API_KEY`. Configure a separate BytePlus API key, balance, and model activation; key presence does not prove account eligibility, access, rate quota, or live generation success. The skill does not create accounts, top up, purchase plans, or reuse domestic balances.

`asset://` IDs require `provenance.provider` matching the target supplier. Independently resolve the supplier/account's material and portrait trust eligibility. Do not submit a domestic asset ID to BytePlus or assume an Ark-trusted human portrait is trusted overseas. Generic public product references may be reused only when suitable and authorized; every offer shows its actual transmitted assets.

## Official sources

- [Quick start and key/API usage](https://docs.byteplus.com/en/docs/modelark/quick-start)
- [Model list](https://docs.byteplus.com/en/docs/modelark/model-list)
- [Price list, formula and minimum-token rule](https://docs.byteplus.com/en/docs/modelark/model-pricing)
- [Create video task API](https://docs.byteplus.com/en/docs/modelark/create-video-generation-task-api)
- [Retrieve video task API](https://docs.byteplus.com/en/docs/modelark/get-video-generation-task-api)
- [Video tutorial and pixel mapping](https://docs.byteplus.com/en/docs/modelark/video-generation-tutorial)
- [Image API](https://docs.byteplus.com/en/docs/modelark/image-generation-api)
- [Seedream Pro/Flash tutorial](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro)
