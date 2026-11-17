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
- **Destaques do Radar Mundial atualizados automaticamente** pelo mesmo coletor RSS/USGS. O GitHub Actions está agendado nos minutos **07 e 37 de cada hora** (UTC), aproximadamente a cada 30 minutos; a execução pode atrasar conforme o serviço GitHub.
- O script `scripts/atualizar_destaques.py` seleciona até 8 notícias internacionais recentes de fontes jornalísticas reconhecidas, prioriza manchetes e resumos em português e grava `destaques-radar.json`.
- Enquanto o site permanece aberto, os destaques são consultados a cada 5 minutos e novamente quando o usuário retorna à aba. Notícias novas aparecem depois que os arquivos são atualizados no GitHub.
- Quando não há novidade relevante, as matérias permanecem visíveis com suas datas originais e o horário da última checagem, sem criar notícias ou mudar a data de publicação.
- **Fonte adicional "Radar Mundial — Seleção do ChatGPT"**: notícias que foram enviadas aqui ficam disponíveis no arquivo `curadoria-chatgpt.json`, identificado como curadoria, **não como veículo jornalístico independente**. Cada matéria traz o nome e link da fonte original.
- A automação de alertas mundiais do ChatGPT foi instruída a **tentar adicionar ao arquivo cada novo alerta confirmado**, após verificar duplicidade, quando o GitHub estiver acessível. Ela é independente das notícias coletadas pelo GitHub Actions e pode falhar caso o conector esteja indisponível.
- O site consulta os registros de curadoria a cada cinco minutos quando está aberto, e ao reabrir a aba. A data da notícia não é substituída pela data da checagem.
- Notificações locais **enquanto o aplicativo/site estiver em execução**, conforme permissão do navegador.

## Limitações
- **Não é um APK nativo nem está na Play Store/App Store.** Para as lojas, é necessário um empacotamento e publicação adicionais.
- **Não há push em segundo plano com o app fechado.** Isso exige serviço de envio (Web Push com assinaturas, armazenamento, chaves VAPID e backend) e permissões do usuário.
- As notícias novas dependem da execução bem-sucedida do workflow `.github/workflows/atualizar-noticias.yml`. Sem feed salvo, a interface busca terremotos do USGS.
- Não são mostradas notícias fictícias.
