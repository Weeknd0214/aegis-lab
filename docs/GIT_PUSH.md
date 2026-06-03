# HSAP 推送到 git.sanyele.com

## 为什么 SSH 一直 Permission denied？

经检测，`git.sanyele.com:22` 返回的是 **Ubuntu 系统 OpenSSH**，不是 Gitea 的 Git SSH 服务。

因此：

- 在 Gitea 网页里添加的 SSH 公钥 **不会** 在 22 端口生效
- 终端问 `git@git.sanyele.com's password` 时，填 Gitea 登录密码 **永远不对**

**结论：请使用 HTTPS + Personal Access Token 推送。**

---

## HTTPS 推送步骤

### 1. 生成 Token

1. 登录 https://git.sanyele.com（`Chengfang.LU@hx-electronics.com`）
2. **设置** → **应用** → **生成新令牌**
3. 名称：`HSAP-push`
4. 权限：勾选 **`write:repository`**（或 repo 写权限）
5. 生成后 **复制 Token**（只显示一次）

### 2. 配置 remote（已默认 HTTPS）

```bash
cd ~/DATA/HSAP
git remote set-url origin https://git.sanyele.com/ChengFang.LU/HSAP.git
```

### 3. Push（在系统终端，不要用 Cursor 内置 Git）

```bash
unset GIT_ASKPASS
export GIT_TERMINAL_PROMPT=1

git push -u origin main
```

提示时：

| 字段 | 填写 |
|------|------|
| Username | `Chengfang.LU@hx-electronics.com` |
| Password | **粘贴 Token**（不是登录密码） |

### 4. 保存凭据（可选）

```bash
git config --local credential.helper store
git push -u origin main
# 输入一次 Token 后会记住
```

---

## 若仍 401

- 确认仓库 `ChengFang.LU/HSAP` 已创建且你有写权限
- 清除错误缓存：`printf "protocol=https\nhost=git.sanyele.com\n\n" | git credential reject`
- 联系管理员确认是否 **仅允许 HTTPS**，以及 Token 权限策略

---

## 需要 SSH 时

请联系 Git 管理员确认：

- Gitea SSH 是否启用、监听端口（非 22）
- 是否有内网/VPN 专用地址（如 `git-ssh.xxx.com:2222`）

在管理员提供正确 SSH 地址前，请使用 HTTPS + Token。
