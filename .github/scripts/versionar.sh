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
# ou ja ter sido tocado manualmente) - exceto quando ja existe um
# pre-release cortado neste ciclo (ver "Pre-release em release/*" abaixo),
# caso em que o alvo (nova) e reaproveitado em vez de recalculado.
#
# Pre-release em release/* ("-hml.N"):
#   Toda release/* so produz pre-release (ex.: 1.0.0-hml.1) ate o PR dela
#   para a main ser aprovado por um code owner - so ai (FINALIZAR=true,
#   chamado por automacao-finaliza-versao-aprovada.yml) o sufixo "-hml.N"
#   e removido e a versao final (1.0.0) e gravada, direto na release/*.
#   Como o merge para a main e squash, a main so ve a versao ja limpa -
#   nao precisa de nenhum push direto na main pra isso. fix/hotfix-* nunca
#   passa por pre-release (vai direto pra versao final, urgencia).
#
# Protecao contra loop: o push do commit de bump usa GH_TOKEN (um PAT de
# verdade, que dispara o proprio workflow de novo - diferente do
# GITHUB_TOKEN padrao). Sem tag de producao ainda, "desde a ultima tag"
# cai pra "desde o inicio do historico", e o mesmo commit de breaking
# change seria encontrado de novo a cada rodada, bumpando sem parar. Por
# isso: se o commit mais recente ja e um bump nosso, e nao e uma chamada
# de FINALIZAR, nao ha nada novo a versionar - para aqui.
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
FINALIZAR="${FINALIZAR:-false}"

if [ "$FINALIZAR" != "true" ] &&
  git log -1 --format=%s | grep -qE '^chore: versiona [0-9]+\.[0-9]+\.[0-9]+(-hml\.[0-9]+)? \('; then
  echo "Commit mais recente já é um bump de versão (evita loop) - nada a fazer."
  echo "incrementou=false" >>"$GITHUB_OUTPUT"
  exit 0
fi

# Proteção contra loop: o commit de bump é empurrado com um PAT de verdade
# (GH_TOKEN), que dispara o próprio workflow de novo (diferente do
# GITHUB_TOKEN padrão). Sem tag de produção ainda, "desde a última tag" cai
# pra "desde o início do histórico" - o mesmo commit de breaking change seria
# encontrado de novo a cada rodada, bumpando sem parar (visto na prática:
# 1.0.0 -> 2.0.0 -> 3.0.0...). Se o commit mais recente já é um bump nosso,
# não há nada novo a versionar - para aqui.
if git log -1 --format=%s | grep -qE '^chore: versiona [0-9]+\.[0-9]+\.[0-9]+ \('; then
  echo "Commit mais recente já é um bump de versão (evita loop) - nada a fazer."
  echo "incrementou=false" >>"$GITHUB_OUTPUT"
  exit 0
fi

git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
git config user.name "versionamento-bot"
git config user.email "actions@github.com"

git fetch origin main --tags --quiet

atual=$(grep -m1 '^version' "$PYPROJECT" | cut -d'"' -f2)

# Ja existe um pre-release cortado neste ciclo (ex.: "1.0.0-hml.2")? Reaproveita
# o alvo (nova) em vez de recalcular - recalcular leria o proprio "1.0.0" ja
# gravado como base e bumparia de novo por cima (o mesmo bug do loop, so que
# manifestado em duas chamadas em vez de N).
if [[ "$atual" =~ ^([0-9]+\.[0-9]+\.[0-9]+)-hml\.([0-9]+)$ ]]; then
  nova="${BASH_REMATCH[1]}"
  contador="${BASH_REMATCH[2]}"
  echo "Pre-release já cortado neste ciclo - reaproveitando alvo $nova (contador atual: $contador)"
else
  contador=0
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
    base="$atual"
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
fi

# release/* so vira versao final quando FINALIZAR=true (aprovacao do PR pela
# main); fix/hotfix-* nunca tem pre-release - vai direto pra versao final.
if [[ "$BRANCH" == release/* ]] && [ "$FINALIZAR" != "true" ]; then
  final="${nova}-hml.$((contador + 1))"
else
  final="$nova"
fi

if [ "$atual" = "$final" ]; then
  echo "Versao ja esta correta ($atual), nada a fazer."
  echo "incrementou=false" >>"$GITHUB_OUTPUT"
  exit 0
fi

sed "0,/^version = \"$atual\"/s//version = \"$final\"/" "$PYPROJECT" >"$PYPROJECT.tmp"
mv "$PYPROJECT.tmp" "$PYPROJECT"

git add "$PYPROJECT"
git commit -m "chore: versiona $final (desde ${ultima_tag:-o início do histórico})"
git push origin "HEAD:$BRANCH"
echo "Versao atualizada: $atual -> $final"
echo "incrementou=true" >>"$GITHUB_OUTPUT"
