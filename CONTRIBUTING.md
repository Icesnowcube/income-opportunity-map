# 贡献指南

欢迎补充不同兴趣的交易结构示例、遗漏的参与位置、公开可核验的案例，或修复指令与工具问题。

## 内容要求

每条机会写清楚：谁付钱、买什么、作者/使用者承担什么角色、怎样收费。入口可以是假设，必须标明；未研究的地方写未知，不编造订单或收入。

保留 `explore`、`research`、`compare`、`validate` 的边界。不要让默认发散变成自动推荐，不把换平台重复计算成新模式。

公开案例使用原始或官方来源，并记录查阅日期、地区和资格；具体收费机制存在不代表一般用户能盈利。贡献通用案例，不提交私人聊天、客户名单、后台截图、Token 或未获授权的作品。

## 修改和检查

修改后运行：

```bash
python3 -B scripts/validate_package.py --skip-manifest
python3 -B scripts/update_manifest.py
python3 -B scripts/validate_package.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

自动化回归不运行宿主模型。涉及触发范围、工作流或格式的修改，另按 `tests/acceptance-cases.md` 做人工验收，在 Pull Request 中写明已测与未测。

## 提交建议

一个 Pull Request 尽量只处理一个问题。说明动机、修改文件、验证命令与重要限制。提交贡献时，请确认有权按本项目 MIT 许可证授权所提交的内容。
