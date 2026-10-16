# deploy/vendor —— 预打包的第三方 wheel

这里只放一个文件：`aisuite-0.1.14-py3-none-any.whl`。

## 为什么需要它

`pyproject.toml` 和 `deploy/requirements-server.txt` 里，aisuite 是**git 依赖**：

```
aisuite @ git+https://github.com/andrewyng/aisuite.git@1b4bbf303ec21968230b1ec869a144d054e9b3c4
```

这在境外机器/本地开发上没问题，但在**中国内地机房**（阿里云北京等）构建时，
`pip` 要去 `github.com` / `codeload.github.com` 拉源码，经常超时或中途断流，
`docker build` 就会停在装依赖这一层失败，而且报错信息很不直观（一串 SSL/EOF）。

所以这个 wheel 是**从同一个 commit 提前打好的**，`deploy/requirements-server.cn.txt`
用它替换那一行 git 依赖，让服务器构建过程完全不依赖 GitHub。

## 它是怎么来的（可复现）

在一台能正常访问 GitHub 的机器上：

```bash
pip download --no-deps --no-binary :all: \
  "aisuite @ git+https://github.com/andrewyng/aisuite.git@1b4bbf303ec21968230b1ec869a144d054e9b3c4" \
  -d /tmp/aisuite_src
pip wheel --no-deps /tmp/aisuite_src/aisuite-0.1.14.zip -w deploy/vendor/
```

产物校验（本次打包的值）：

- 文件名：`aisuite-0.1.14-py3-none-any.whl`
- 大小：228327 bytes
- sha256：`df0c3a6ef55d2d7ac38015cc9610e91490486ebdcd7f26c4bd5a6f2bd3759f8a`

## 什么时候该更新它

只有当 `pyproject.toml` 里 aisuite 的 commit 改了，才需要按上面两条命令重新打一次，
否则服务器上装的仍然是旧 commit（版本号可能一样，但代码不一样，很难排查）。
