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
- **Coleta RSS/USGS agendada a cada 5 minutos** pelo GitHub Actions (cron `2-59/5 * * * *`, UTC), o menor intervalo periódico permitido pelo GitHub. Execuções podem atrasar ou, em períodos de carga, não ocorrer; o site não é um canal de notícias instantâneo.
- O script `scripts/atualizar_destaques.py` seleciona até 8 notícias internacionais recentes de fontes jornalísticas reconhecidas, prioriza manchetes e resumos em português e grava `destaques-radar.json`.
- **Tela inicial com notícias novas:** seção **Acabaram de sair** mostra as manchetes mais recentes em ordem de publicação, com link direto para a fonte original. O feed principal consulta o GitHub **a cada 1 minuto** enquanto estiver aberto e visível; os destaques editoriais seguem consultados a cada 5 minutos.
- **Histórico permanente:** `scripts/arquivar_noticias.py` combina os novos artigos com os meses já arquivados em `historico/AAAA-MM.json`, preservando os anteriores e completando traduções/imagens ausentes posteriormente. O índice `historico/indice.json` lista meses e quantidades. A tela **Histórico de notícias** permite escolher o mês e pesquisar por palavra-chave ou categoria, com carregamento paginado de 24 artigos. O arquivo começa nas notícias disponíveis na primeira execução, sem retroatividade automática.
- Sem cópias integrais de reportagens: são armazenados metadados públicos, títulos/resumos curtos e URLs originais. O script evita duplicatas de links e não altera a curadoria independente do ChatGPT.
- Quando não há novidade relevante, as matérias permanecem visíveis com suas datas originais e o horário da última checagem, sem criar notícias ou mudar a data de publicação.
- **Fonte adicional "Radar Mundial — Seleção do ChatGPT"**: notícias que foram enviadas aqui ficam disponíveis no arquivo `curadoria-chatgpt.json`, identificado como curadoria, **não como veículo jornalístico independente**. Cada matéria traz o nome e link da fonte original.
- A automação de alertas mundiais do ChatGPT foi instruída a **tentar adicionar ao arquivo cada novo alerta confirmado**, após verificar duplicidade, quando o GitHub estiver acessível. Ela é independente das notícias coletadas pelo GitHub Actions e pode falhar caso o conector esteja indisponível.
- O site consulta os registros de curadoria a cada cinco minutos quando está aberto, e ao reabrir a aba. A data da notícia não é substituída pela data da checagem.
- Notificações locais **enquanto o aplicativo/site estiver em execução**, conforme permissão do navegador.

## Limitações
- **Não é um APK nativo nem está na Play Store/App Store.** Para as lojas, é necessário um empacotamento e publicação adicionais.
- **Não há push em segundo plano com o app fechado.** Isso exige serviço de envio (Web Push com assinaturas, armazenamento, chaves VAPID e backend) e permissões do usuário.
- As notícias novas dependem da publicação pelo RSS e da execução bem-sucedida do workflow `.github/workflows/atualizar-noticias.yml`. A coleta a cada 5 minutos é um agendamento, não uma garantia de atraso máximo de 5 minutos. Traduções gratuitas e imagens podem ficar pendentes ou indisponíveis. Sem feed salvo, a interface busca terremotos do USGS.
- O arquivo histórico é cumulativo e cresce no GitHub com o tempo: convém monitorar o tamanho do repositório, limites de armazenamento e políticas de direitos autorais.
- A consulta automática do PWA acontece enquanto ele está aberto/visível; o aplicativo fechado não recebe push sem um backend de notificações próprio.
- Não são mostradas notícias fictícias.
