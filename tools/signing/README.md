# 更新包签名说明

- 私钥必须放在仓库外，通过环境变量 DZFYQ_UPDATE_PRIVATE_KEY 或 --private-key 传入。
- 公钥写入 src/gongju/update_trust.py 的 UPDATE_ED25519_PUBLIC_KEY_B64。
- Windows 全量包签名生成 DZFYQ-SIG-WINDOWS 和兼容旧客户端的 DZFYQ-SIG，发布时同时写入 GitHub 与 Gitee 两端的 Release 说明（每个版本都双端发布）。
- Windows 增量包签名只写入同名 .zip.sig.json，不生成或输出 Release 说明标记。
- Release 必须保留已签名全量包；增量包只能作为精确来源版本的可选下载资源。
