# Alerta Global → Instagram (automático)

A cada 30 minutos, o robô faz o seguinte:

1. lê **todas as notícias** do Alerta Global no arquivo `noticias.json` do repositório `ryderguedes154/alerta-global`;
2. pega as **2 mais recentes** que ainda não foram postadas, publicadas nas últimas 6 horas;
3. cria uma **imagem 1080×1350** com a foto da matéria, a categoria, o título e o crédito da fonte;
4. monta a **descrição** com o Claude, que reescreve o resumo em português com hashtags, ou usa o resumo do site como está (`USAR_CLAUDE=nao`);
5. **publica no Instagram** pela API oficial;
6. guarda o que já foi postado (`publicados.json`), para nunca repetir.

Na primeira execução, ele publica **só a notícia mais recente**, sem despejar o histórico.

### Por que não posta absolutamente todas?
O Instagram aceita **no máximo 100 posts por dia** pela API, e o Alerta Global recebe centenas de notícias por dia. Com 2 posts a cada 30 minutos, são cerca de 96 por dia, sempre as mais novas. Passar disso faz o Instagram recusar os posts e pode bloquear a conta.

> ⚠️ **Direitos autorais:** as fotos são da CNN, BBC, Getty, Reuters etc. Postar essas fotos no Instagram pode gerar denúncias e até a remoção de posts ou da conta. Para usar só um fundo colorido com o título, configure `USAR_IMAGEM_DA_MATERIA=nao`.

---

## Passo 1: chave da API do Claude
*(pule este passo se for usar `USAR_CLAUDE=nao`)*

1. Entre em https://console.anthropic.com, crie a conta e adicione créditos.
2. Vá em **API Keys** → **Create Key** e guarde a chave (começa com `sk-ant-`).

O custo é de cerca de US$ 0,03 por post, o que dá uns US$ 3 por dia com 96 posts.

## Passo 2: preparar o Instagram

1. No app do Instagram, vá em **Configurações → Tipo de conta e ferramentas** e mude para **Conta profissional** (Criador de conteúdo ou Empresa).
2. Entre em https://developers.facebook.com e clique em **Meus apps → Criar app**. Escolha o caso de uso **"Gerenciar mensagens e conteúdo no Instagram"**.
3. No painel do app, abra **Instagram → Configuração da API com login do Instagram**.
4. Em **Gerar tokens de acesso**, clique em **Adicionar conta**, entre com a conta do Instagram e autorize. Precisa ter a permissão `instagram_business_content_publish`.
5. Clique em **Gerar token**. Copie:
   - o **token**, que vai em `IG_ACCESS_TOKEN`;
   - o **ID da conta do Instagram**, o número ao lado da conta, que vai em `IG_USER_ID`.

> ⚠️ Esse token **vence em 60 dias**. Coloque um lembrete para gerar um novo e trocar no GitHub (Passo 4).

## Passo 3: onde o robô fica

O robô fica na pasta `instagram/` do próprio repositório **alerta-global**, e o agendamento fica em `.github/workflows/publicar-instagram.yml`. As imagens são salvas em `instagram/imagens/`, de onde o Instagram as baixa. Como o site também grava no repositório a cada 5 minutos, o robô tenta de novo automaticamente quando os dois gravam ao mesmo tempo.

## Passo 4: colocar as chaves no GitHub

No repositório `alerta-global`, vá em **Settings → Secrets and variables → Actions → aba "Secrets" → New repository secret**:

| Nome | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | a chave do Passo 1 |
| `IG_USER_ID` | o ID da conta do Passo 2 |
| `IG_ACCESS_TOKEN` | o token do Passo 2 |

**Ajustes opcionais**, na aba **"Variables"**. Sem eles, o robô usa estes padrões:

| Nome | Padrão | O que faz |
|---|---|---|
| `MAX_POSTS_POR_EXECUCAO` | `2` | posts a cada 30 minutos |
| `IDADE_MAXIMA_HORAS` | `6` | ignora notícias mais velhas que isso |
| `USAR_IMAGEM_DA_MATERIA` | `sim` | `nao` = fundo colorido sem foto |
| `USAR_CLAUDE` | `sim` | `nao` = descrição igual ao resumo do site, sem custo |
| `HASHTAGS_FIXAS` | vazio | ex.: `#alertaglobal #noticias` |
| `NOTICIAS_JSON_URL` | `noticias.json` do Alerta Global | para usar `destaques-radar.json`, só as 8 manchetes principais |

## Passo 5: testar

Aba **Actions** → **Publicar noticias no Instagram** → **Run workflow**. Em 1 a 2 minutos o post aparece no Instagram. Se falhar, clique na execução para ver o erro.

## Dica
O Instagram não deixa link clicável na legenda, por isso ela diz "link na bio". Coloque o endereço do Alerta Global na bio do perfil.
