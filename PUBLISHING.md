# 首次发布到 GitHub

这是仓库维护者的可选流程，不是运行收入分析 Skill 的步骤。

## 先了解会发生什么

`publish-github.sh` 会在当前登录的 GitHub 账号下创建一个 **public** 仓库，默认名 `income-opportunity-map`。它只发送经校验且位于 `SHA256SUMS` 内的文件及清单本身，不发送源目录的 Git 历史、未列入清单的文件或其他目录。

它不会更改现有仓库的可见性，不会覆盖、删除同名仓库，也不会修改全局 Git 配置。遇到同名仓库会停止；后续更新应在正式仓库中审查后走正常 Git/PR 流程。

发布会公开文件内容和一条初始提交。脚本使用当前 GitHub 登录名和该账号的 GitHub noreply 邮箱生成这条提交，避免读取或上传本机的私人邮箱配置。

## 前提

需要 Python 3.9+、Git 和已登录的 GitHub CLI (`gh`)，以及目标账号/组织下的建库与推送权限。

```bash
gh auth login --hostname github.com
gh auth status --hostname github.com
```

认证应在自己电脑的 CLI/浏览器中完成。**不要把访问令牌、密码或验证码粘贴到聊天、README 或代码里。**

## 运行

先做本地预览；这一步不访问网络、不创建仓库：

```bash
bash publish-github.sh --dry-run
```

确认准备公开后：

```bash
bash publish-github.sh
```

脚本会显示目标并要求确认。已经明确决定时，可显式传 `--yes`：

```bash
bash publish-github.sh --yes
```

指定自己有权限的组织或另一个新仓库名：

```bash
bash publish-github.sh --owner YOUR_ORG --repo income-opportunity-map --yes
```

`YOUR_ORG` 是占位示例，不是已经创建的地址。默认省略 owner 时使用当前认证用户，不猜测账号。

## 成功与失败

只有公开可见性与远端 `main` 提交校验均通过，脚本才打印 `PUBLISHED` 和实际仓库链接。只创建仓库但推送/核验失败时，不能视为发布完成；脚本会提示检查，不会自动删除远端仓库。

本仓库的自动化测试只测试无网络预览及保护逻辑，**不代表已经实际创建或推送 GitHub 仓库**。

官方命令依据见 [sources.md](sources.md)。
