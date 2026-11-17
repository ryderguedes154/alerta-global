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
- **Histórico móvel de 15 dias:** `scripts/arquivar_noticias.py` armazena notícias RSS em `historico/AAAA-MM.json`. Após a coleta, `scripts/limpar_noticias_antigas.py` retira das cópias correntes os registros publicados há mais de 15 dias e apaga os arquivos mensais que ficarem vazios. O índice `historico/indice.json` é atualizado. A aba **Histórico** permite escolher mês, pesquisar por assunto/categoria e selecionar **Todas as notícias / Alertas do ChatGPT / RSS**. Os alertas do ChatGPT são exibidos a partir do arquivo próprio, sem copiá-los como RSS. Paginação de 24 matérias.
- Sem cópias integrais de reportagens: são armazenados metadados públicos, títulos/resumos curtos e URLs originais. O script evita duplicatas de links e não altera a curadoria independente do ChatGPT.
- Quando não há novidade relevante, as matérias permanecem visíveis com suas datas originais e o horário da última checagem, sem criar notícias ou mudar a data de publicação.
- **Fonte adicional "Radar Mundial — Seleção do ChatGPT"**: os alertas novos do ChatGPT são gravados em `curadoria-chatgpt.json` durante a execução do monitor, com `saved_at` (UTC), e entram na janela móvel de **15 dias desde o armazenamento**; registros legados sem `saved_at` usam a data disponível da matéria. Uma rotina do GitHub também elimina alertas expirados desse arquivo. O ChatGPT é apenas o curador, **não a fonte jornalística original**; a matéria indica o veículo oficial e URL.
- A automação de alertas mundiais do ChatGPT foi instruída a **tentar adicionar ao arquivo cada novo alerta confirmado**, após verificar duplicidade, quando o GitHub estiver acessível. Ela é independente das notícias coletadas pelo GitHub Actions e pode falhar caso o conector esteja indisponível.
- O site consulta os registros da curadoria ChatGPT **a cada minuto** enquanto está aberto e novamente ao reabrir a aba; após cada commit do ChatGPT na branch `main`, as notícias passam a aparecer na consulta seguinte, sujeito à disponibilidade do GitHub e da rede. Esse tempo não muda a frequência **horária** do monitor ChatGPT nem garante sincronização caso a escrita falhe.
- Notificações locais **enquanto o aplicativo/site estiver em execução**, conforme permissão do navegador.

## Limitações
- **Não é um APK nativo nem está na Play Store/App Store.** Para as lojas, é necessário um empacotamento e publicação adicionais.
- **Não há push em segundo plano com o app fechado.** Isso exige serviço de envio (Web Push com assinaturas, armazenamento, chaves VAPID e backend) e permissões do usuário.
- As notícias novas dependem da publicação pelo RSS e da execução bem-sucedida do workflow `.github/workflows/atualizar-noticias.yml`. A coleta a cada 5 minutos é um agendamento, não uma garantia de atraso máximo de 5 minutos. Traduções gratuitas e imagens podem ficar pendentes ou indisponíveis. Sem feed salvo, a interface busca terremotos do USGS.
- A janela de 15 dias vale para os **arquivos exibidos no site e para os arquivos atuais da branch main**; o GitHub ainda preserva versões antigas em seu **histórico de commits**. A exclusão permanente dos commits antigos exige outra arquitetura de armazenamento/expurgo, não coberta por esta implementação. Também convém respeitar os direitos autorais.
- A consulta automática do PWA acontece enquanto ele está aberto/visível; o aplicativo fechado não recebe push sem um backend de notificações próprio.
- Não são mostradas notícias fictícias.
