# Chunk 抽检样例（seed=42，共抽 10 条）

> char_span 回切一致性：10/10 通过


## 样例 1：`tutorial.path-params-numeric-validations#0002`

- 文档：`tutorial/path-params-numeric-validations.md`｜章节：**路径参数和数值校验 > 导入 `Path`**｜char_span `[512, 707)`｜195 字符｜span 回切一致：✅

**上文（前 80 字符）**：`}⏎    if q:⏎        results.update({"q": q})⏎    return results⏎```⏎⏎**📝 注意：**⏎⏎`

**chunk 全文**：

```markdown
FastAPI 在 0.95.0 版本添加了对 `Annotated` 的支持（并开始推荐使用它）。

如果你使用的是更旧的版本，尝试使用 `Annotated` 会报错。

请确保在使用 `Annotated` 之前，将 FastAPI 版本[升级](../deployment/versions.md#upgrading-the-fastapi-versions)到至少 0.95.1。
```

**下文（后 80 字符）**：`⏎⏎你可以声明与 `Query` 相同的所有参数。⏎⏎例如，要为路径参数 `item_id` 声明 `title` 元数据值，你可以这样写：⏎⏎```pytho`

---

## 样例 2：`advanced.path-operation-advanced-configuration#0009`

- 文档：`advanced/path-operation-advanced-configuration.md`｜章节：**路径操作的高级配置 > OpenAPI Extra > OpenAPI 扩展**｜char_span `[3032, 3504)`｜472 字符｜span 回切一致：✅

**上文（前 80 字符）**：`⏎[图片]⏎⏎如果你查看最终生成的 OpenAPI（在你的 API 的 `/openapi.json`），你也会看到你的扩展作为该 *路径操作* 的一部分：⏎⏎`

**chunk 全文**：

```markdown
```JSON
{
    "openapi": "3.1.0",
    "info": {
        "title": "FastAPI",
        "version": "0.1.0"
    },
    "paths": {
        "/items/": {
            "get": {
                "summary": "Read Items",
                "operationId": "read_items_items__get",
                "responses": {
                    "200": {
                        "description": "Successful Response",
                        "content": {
                            "application/json": {
```

**下文（后 80 字符）**：`⏎                                "schema": {}⏎                            }⏎    `

---

## 样例 3：`advanced.advanced-dependencies#0021`

- 文档：`advanced/advanced-dependencies.md`｜章节：**高级依赖项 > 带 `yield` 的依赖项、`HTTPException`、`except` 与后台任务 > 后台任务与带 `yield` 的依赖项（技术细节）**｜char_span `[6639, 6797)`｜158 字符｜span 回切一致：✅

**上文（前 80 字符）**：`外，后台任务通常是一段独立的逻辑，应该单独处理，并使用它自己的资源（例如它自己的数据库连接）。⏎⏎因此，这样做你的代码通常会更清晰。⏎⏎如果你过去依赖于旧行为，`

**chunk 全文**：

```markdown
现在应在后台任务内部自行创建所需资源，并且只在内部使用不依赖于带 `yield` 依赖项资源的数据。

例如，不要复用相同的数据库会话，而是在后台任务内部创建一个新的会话，并用这个新会话从数据库获取对象。然后，不是把数据库对象本身作为参数传给后台任务函数，而是传递该对象的 ID，并在后台任务函数内部再次获取该对象。
```

**下文（后 80 字符）**：``

---

## 样例 4：`tutorial.schema-extra-example#0017`

- 文档：`tutorial/schema-extra-example.md`｜章节：**声明请求示例数据 > JSON Schema 中的 `examples` - OpenAPI > 使用 `openapi_examples` 参数**｜char_span `[4265, 4659)`｜394 字符｜span 回切一致：✅

**上文（前 80 字符）**：`都包含会被添加到 **OpenAPI** 的额外信息。⏎⏎这不放在 OpenAPI 内部包含的各个 JSON Schema 里，而是直接放在*路径操作*上。⏎⏎`

**chunk 全文**：

```markdown
你可以在 FastAPI 中通过参数 `openapi_examples` 来声明这个 OpenAPI 特定的 `examples`，适用于：

- `Path()`
- `Query()`
- `Header()`
- `Cookie()`
- `Body()`
- `Form()`
- `File()`

这个 `dict` 的键用于标识每个示例，每个值是另一个 `dict`。

`examples` 中每个具体示例的 `dict` 可以包含：

- `summary`：该示例的简短描述。
- `description`：较长描述，可以包含 Markdown 文本。
- `value`：实际展示的示例，例如一个 `dict`。
- `externalValue`：`value` 的替代项，指向该示例的 URL。不过它的工具支持度可能不如 `value`。

你可以这样使用：
```

**下文（后 80 字符）**：`⏎⏎```python⏎from typing import Annotated⏎⏎from fastapi import Body, FastAPI⏎from`

---

## 样例 5：`deployment.https#0004`

- 文档：`deployment/https.md`｜章节：**关于 HTTPS > Let's Encrypt**｜char_span `[1490, 1819)`｜329 字符｜span 回切一致：✅

**上文（前 80 字符）**：`用作 TLS 终止代理的一些选项包括：⏎⏎* Traefik（也可以处理证书更新）⏎* Caddy（也可以处理证书更新）⏎* Nginx⏎* HAProxy⏎⏎`

**chunk 全文**：

```markdown
在 Let's Encrypt 之前，这些 **HTTPS 证书** 由受信任的第三方出售。

过去，获得这些证书的过程非常繁琐，需要大量的文书工作，而且证书非常昂贵。

但随后 **[Let's Encrypt](https://letsencrypt.org/)** 创建了。

它是 Linux 基金会的一个项目。 它以自动方式免费提供 **HTTPS 证书**。 这些证书可以使用所有符合标准的安全加密，并且有效期很短（大约 3 个月），因此**安全性实际上更好**，因为它们的生命周期缩短了。

域可以被安全地验证并自动生成证书。 这还允许自动更新这些证书。

我们的想法是自动获取和更新这些证书，以便你可以永远免费拥有**安全的 HTTPS**。
```

**下文（后 80 字符）**：`⏎⏎这里有一个 HTTPS API 看起来是什么样的示例，我们会分步说明，并且主要关注对开发人员重要的部分。⏎⏎第一步我们要先**获取**一些**域名(Doma`

---

## 样例 6：`deployment.concepts#0021`

- 文档：`deployment/concepts.md`｜章节：**部署概念 > 复制 - 进程和内存 > 服务器内存**｜char_span `[3899, 4087)`｜188 字符｜span 回切一致：✅

**上文（前 80 字符）**：`⏎⏎多个进程通常**不共享任何内存**。这意味着每个正在运行的进程都有自己的东西、变量和内存。如果你的代码消耗了大量内存，**每个进程**将消耗等量的内存。⏎⏎`

**chunk 全文**：

```markdown
例如，如果你的代码加载**大小为 1 GB** 的机器学习模型，则当你使用 API 运行一个进程时，它将至少消耗 1 GB RAM。如果你启动 **4 个进程**（4 个工作进程），每个进程将消耗 1 GB RAM。因此，你的 API 总共将消耗 **4 GB RAM**。

如果你的远程服务器或虚拟机只有 3 GB RAM，尝试加载超过 4 GB RAM 将导致问题。 🚨
```

**下文（后 80 字符）**：`⏎⏎在此示例中，有一个 **Manager Process** 启动并控制两个 **Worker Processes**。⏎⏎该管理器进程可能是监听 IP 中的`

---

## 样例 7：`async#0015`

- 文档：`async.md`｜章节：**并发 async / await > 异步代码 > 并发 + 并行: Web + 机器学习**｜char_span `[5105, 5380)`｜275 字符｜span 回切一致：✅

**上文（前 80 字符）**：`器学习的一个子领域，同样适用。只是没有一个数字的电子表格可以相乘，而是一个庞大的数字集合，在很多情况下，你需要使用一个特殊的处理器来构建和/或使用这些模型。⏎⏎`

**chunk 全文**：

```markdown
使用 **FastAPI**，你可以利用 Web 开发中常见的并发机制的优势（NodeJS 的主要吸引力）。

并且，你也可以利用并行和多进程（让多个进程并行运行）的优点来处理与机器学习系统中类似的 **CPU 密集型** 工作。

这一点，再加上 Python 是**数据科学**、机器学习（尤其是深度学习）的主要语言这一简单事实，使得 **FastAPI** 与数据科学/机器学习 Web API 和应用程序（以及其他许多应用程序）非常匹配。

了解如何在生产环境中实现这种并行性，可查看此文 [部署](deployment/index.md)。
```

**下文（后 80 字符）**：`⏎⏎现代版本的 Python 有一种非常直观的方式来定义异步代码。这使它看起来就像正常的“顺序”代码，并在适当的时候为你“等待”。⏎⏎当有一个操作需要等待才能给`

---

## 样例 8：`advanced.security.oauth2-scopes#0010`

- 文档：`advanced/security/oauth2-scopes.md`｜章节：**OAuth2 作用域 > 带作用域的 JWT 令牌**｜char_span `[3395, 3869)`｜474 字符｜span 回切一致：✅

**上文（前 80 字符）**：`），并添加了更多的作用域需求。⏎⏎在这个例子里，它需要作用域 `me`（也可以需要多个作用域）。⏎⏎**📝 注意：**⏎⏎不必在不同位置添加不同的作用域。⏎⏎这`

**chunk 全文**：

```markdown
里这样做，是为了演示 **FastAPI** 如何处理在不同层级声明的作用域。

```python

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, Validatio…（超长行已截断，原 5522 字符）

**📝 技术细节：**
```

**下文（后 80 字符）**：`⏎⏎`Security` 实际上是 `Depends` 的子类，它只多了一个我们稍后会看到的参数。⏎⏎但当你使用 `Security` 而不是 `Depends`

---

## 样例 9：`tutorial.schema-extra-example#0007`

- 文档：`tutorial/schema-extra-example.md`｜章节：**声明请求示例数据 > JSON Schema 中的 `examples` - OpenAPI**｜char_span `[1860, 2029)`｜169 字符｜span 回切一致：✅

**上文（前 80 字符）**：`Item):⏎    results = {"item_id": item_id, "item": item}⏎    return results⏎```⏎⏎`

**chunk 全文**：

```markdown
在以下任意场景中使用：

- `Path()`
- `Query()`
- `Header()`
- `Cookie()`
- `Body()`
- `Form()`
- `File()`

你也可以声明一组 `examples`，这些带有附加信息的示例将被添加到它们在 **OpenAPI** 中的 **JSON Schema** 里。
```

**下文（后 80 字符）**：`⏎⏎这里我们向 `Body()` 传入 `examples`，其中包含一个期望的数据示例：⏎⏎```python⏎from typing import Anno`

---

## 样例 10：`advanced.openapi-callbacks#0013`

- 文档：`advanced/openapi-callbacks.md`｜章节：**OpenAPI 回调 > 常规 **FastAPI** 应用 > 创建回调*路径操作***｜char_span `[4577, 4947)`｜370 字符｜span 回切一致：✅

**上文（前 80 字符）**：`传入该回调路由的 `.routes` 属性：⏎⏎```python⏎⏎from fastapi import APIRouter, FastAPI⏎from p`

**chunk 全文**：

```markdown
ydantic import BaseModel, HttpUrl

app = FastAPI()

class Invoice(BaseModel):
    id: str
    title: str | None = None
    customer: str
    total: float

class InvoiceEvent(BaseModel):
    description: str
    paid: bool

class InvoiceEventReceived(BaseModel):
    ok: bool

invoices_callback_router = APIRouter()

@invoices_callback_route…（超长行已截断，原 1346 字符）

**💡 提示：**
```

**下文（后 80 字符）**：`⏎⏎请注意，你不是把路由本身（`invoices_callback_router`）传给 `callbacks=`，而是传它的 `.routes`，也就是 `i`

---
