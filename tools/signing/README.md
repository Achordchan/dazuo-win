# 更新包签名说明

- 私钥请放在仓库外，通过环境变量 `DZFYQ_UPDATE_PRIVATE_KEY` 或 `--private-key` 传入。
- 公钥写入 `src/gongju/update_trust.py` 的 `UPDATE_ED25519_PUBLIC_KEY_B64`。
- 使用 `tools/sign_windows_update_package.py` 为更新 zip 生成签名，并把输出的 `DZFYQ-SIG:...` 写入 Gitee Release 说明。
