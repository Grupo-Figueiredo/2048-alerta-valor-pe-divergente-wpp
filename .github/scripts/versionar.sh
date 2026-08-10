#!/usr/bin/env bash
# Calcula e aplica a proxima versao semantica (major.minor.patch, no
# significado classico) a partir dos commits acumulados na branch atual
# (release/* ou hotfix/*) desde a ultima tag de producao.
#
# Prioridade de decisao:
#   1. Label version:major / version:minor / version:patch no PR desta
#      branch para a main, se ele ja existir e tiver uma dessas labels.
#   2. Sem label: varre as mensagens de commit desde a ultima tag (nao a
#      "-hml") em busca do maior nivel presente:
#        - "!" depois do tipo (ex.: fix!:) ou "BREAKING CHANGE" no corpo -> major
#        - "feat:" (sem quebra)                                          -> minor
#        - qualquer outro tipo (fix, chore, refactor, docs, etc.)        -> patch
#
# A versao base para o incremento e sempre a ultima tag de producao (nunca
# o valor atual do pyproject.toml na branch, que pode estar desatualizado
# ou ja ter sido tocado manualmente).
#
# Requisitos do ambiente: checkout com fetch-depth: 0, GH_TOKEN no
# ambiente (PAT do Admin - necessario tanto para o push, que precisa
# pular o ruleset protect-release/protect-dev, quanto para o gh CLI
# consultar a label do PR), e BRANCH_NOME com o nome real da branch.
#
# BRANCH_NOME precisa ser passado explicitamente pelo workflow chamador -
# nao usamos GITHUB_REF_NAME direto porque, no workflow disparado por
# label (pull_request), esse valor vem como "123/merge" (a ref sintetica
# do PR), nao o nome da branch de origem. Sem GH_TOKEN configurado, a
# consulta de label falha em silencio (cai na deteccao automatica) mas o
# push final falha - ver pendencia "secret GH_TOKEN ausente" no README.
set -euo pipefail

PYPROJECT="pyproject.toml"
BRANCH="${BRANCH_NOME:?defina BRANCH_NOME com o nome da branch}"

git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
git config user.name "versionamento-bot"
git config user.email "actions@github.com"

git fetch origin main --tags --quiet

ultima_tag=$(git tag --list 'v*' | grep -Ev -- '-hml$' | sort -V | tail -1 || true)

# 1) Sobrescrita por label no PR desta branch para a main.
nivel=""
pr_numero=$(gh pr list --head "$BRANCH" --base main --state open --json number --jq '.[0].number // empty' 2>/dev/null || true)
if [ -n "$pr_numero" ]; then
  label=$(gh pr view "$pr_numero" --json labels --jq '.labels[].name' 2>/dev/null | grep -m1 '^version:' || true)
  if [ -n "$label" ]; then
    nivel="${label#version:}"
    echo "Sobrescrita por label no PR #$pr_numero: $label"
  fi
fi

# 2) Sem label: varre os commits desde a ultima tag de producao.
if [ -z "$nivel" ]; then
  if [ -n "$ultima_tag" ]; then
    intervalo="$ultima_tag..HEAD"
  else
    intervalo="HEAD"
  fi
  corpo=$(git log "$intervalo" --format=%B || true)

  if echo "$corpo" | grep -qE '^[a-z]+(\([a-z0-9._/-]+\))?!:' || echo "$corpo" | grep -q 'BREAKING CHANGE'; then
    nivel="major"
  elif echo "$corpo" | grep -qE '^feat(\([a-z0-9._/-]+\))?:'; then
    nivel="minor"
  else
    nivel="patch"
  fi
  echo "Nivel detectado pelos commits desde ${ultima_tag:-o inicio do historico}: $nivel"
fi

# 3) Versao base = ultima tag de producao.
if [ -n "$ultima_tag" ]; then
  base="${ultima_tag#v}"
else
  base=$(grep -m1 '^version' "$PYPROJECT" | cut -d'"' -f2)
fi

major=$(echo "$base" | cut -d. -f1)
minor=$(echo "$base" | cut -d. -f2)
patch=$(echo "$base" | cut -d. -f3)

case "$nivel" in
  major)
    major=$((major + 1))
    minor=0
    patch=0
    ;;
  minor)
    minor=$((minor + 1))
    patch=0
    ;;
  patch)
    patch=$((patch + 1))
    ;;
  *)
    echo "::error::nivel invalido: '$nivel'"
    exit 1
    ;;
esac

nova="$major.$minor.$patch"
atual=$(grep -m1 '^version' "$PYPROJECT" | cut -d'"' -f2)

if [ "$atual" = "$nova" ]; then
  echo "Versao ja esta correta ($atual), nada a fazer."
  echo "incrementou=false" >>"$GITHUB_OUTPUT"
  exit 0
fi

sed "0,/^version = \"$atual\"/s//version = \"$nova\"/" "$PYPROJECT" >"$PYPROJECT.tmp"
mv "$PYPROJECT.tmp" "$PYPROJECT"

git add "$PYPROJECT"
git commit -m "chore: versiona $nova ($nivel, desde ${ultima_tag:-o inicio do historico})"
git push origin "HEAD:$BRANCH"
echo "Versao atualizada: $atual -> $nova ($nivel)"
echo "incrementou=true" >>"$GITHUB_OUTPUT"
