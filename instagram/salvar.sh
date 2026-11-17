#!/usr/bin/env bash
# Salva imagens/fila/historico do robo do Instagram no repositorio.
# O site tambem grava no repositorio a cada 5 minutos, entao tenta de novo
# (pegando as alteracoes mais recentes) se o envio for recusado.
set -e
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A .   # so a pasta instagram/ (o workflow roda dentro dela)
if git diff --cached --quiet; then
  echo "Nada para salvar."
  exit 0
fi
git commit -m "$1"
for tentativa in 1 2 3 4 5; do
  if git pull --rebase origin main && git push origin HEAD:main; then
    exit 0
  fi
  echo "Envio recusado (tentativa $tentativa), tentando de novo..."
  sleep $((tentativa * 5))
done
echo "Nao foi possivel enviar para o repositorio."
exit 1
