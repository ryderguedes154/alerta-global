# 🌍 Alerta Global + Radar Mundial
Aplicativo web progressivo (PWA) para acompanhar notícias internacionais, riscos globais e terremotos.

## Instalar
O aplicativo precisa estar **publicado em HTTPS** (por exemplo, no GitHub Pages).
1. No GitHub do repositório, entre em **Settings > Pages > Build and deployment**, selecione **Deploy from a branch**, branch **main** e pasta **/(root)**. Salve.
2. Abra a URL publicada no celular. No Android (Chrome), toque em **Instalar app** ou abra o menu ⋮ > **Instalar aplicativo**.
3. No iPhone (Safari), toque em **Compartilhar > Adicionar à Tela de Início**.
4. No computador (Chrome/Edge), clique em **Instalar app** ou no ícone de instalação na barra do navegador.

## O que está pronto
- Instalação com ícone em Android, iOS e desktop via PWA.
- Abertura em tela própria, como aplicativo.
- Service worker que mantém a interface e, após a primeira consulta bem-sucedida, as últimas notícias em cache para leitura sem conexão.
- Radar Mundial, filtros e fontes RSS/USGS coletadas por GitHub Actions.
- Notificações locais **enquanto o aplicativo/site estiver em execução**, conforme permissão do navegador.

## Limitações
- **Não é um APK nativo nem está na Play Store/App Store.** Para as lojas, é necessário um empacotamento e publicação adicionais.
- **Não há push em segundo plano com o app fechado.** Isso exige serviço de envio (Web Push com assinaturas, armazenamento, chaves VAPID e backend) e permissões do usuário.
- As notícias novas dependem da execução bem-sucedida do workflow `.github/workflows/atualizar-noticias.yml`. Sem feed salvo, a interface busca terremotos do USGS.
- Não são mostradas notícias fictícias.
