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
# Tag de homologacao (release/* -> "vX.Y.Z-hml"):
#   Toda release/* ganha, a cada push, uma tag "vX.Y.Z-hml" movel apontando
#   pro commit mais novo - marca o build de homologacao. pyproject.toml
#   grava direto a versao final "X.Y.Z", sem sufixo nenhum: e um numero de
#   pacote Python (PEP 440), nao aceita sufixo tipo "-hml" (uv/hatchling
#   recusam o pyproject.toml). A tag final "vX.Y.Z" (sem sufixo) nasce sem
#   nenhuma mudanca aqui: e o `_reusable-build.yml` que ja cria essa tag,
#   depois do build que so acontece no merge pra `main` - que so acontece
#   depois de aprovacao de code owner. fix/hotfix-* nunca ganha tag "-hml"
#   (vai direto pra versao final, e urgencia).
#
#   Uma tag sozinha nao aparece na aba Releases do GitHub nem ganha o badge
#   "Pre-release" - por isso o script tambem cria (so na primeira vez) uma
#   Release apontando pra essa tag, com `--prerelease`. So cria se ainda nao
#   existe: a mesma tag "-hml" se move a cada push desta release/*, e uma
#   nota de release escrita a mao (o time costuma detalhar o que foi testado)
#   nao deve ser apagada por uma rodada nova de CI.
#
# Protecao contra loop: o push do commit de bump usa GH_TOKEN (um PAT de
# verdade, que dispara o proprio workflow de novo - diferente do
# GITHUB_TOKEN padrao). Sem tag de producao ainda, "desde a ultima tag"
# cai pra "desde o inicio do historico", e o mesmo commit de breaking
# change seria encontrado de novo a cada rodada, bumpando sem parar. Por
# isso: se o commit mais recente ja e um bump nosso, nao ha nada novo a
# versionar - mas a tag "-hml" (se for release/*) ainda e movida pro commit
# atual antes de sair, ja que o push anterior pode ter sido so o bump.
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
atual=$(grep -m1 '^version' "$PYPROJECT" | cut -d'"' -f2)

# Ja existe uma tag "-hml" cortada neste ciclo, alcancavel a partir do HEAD
# atual? Reaproveita a versao dela em vez de recalcular - sem isso, um novo
# commit de correcao (ex.: apos feedback de homologacao) recalcularia do
# zero, leria o "atual" ja bumpado como base e bumparia de novo por cima
# (o mesmo bug do loop, so que disparado por commit de verdade em vez de
# auto-retrigger do proprio push).
nova_existente=""
for t in $(git tag -l 'v*-hml'); do
  if git merge-base --is-ancestor "$t" HEAD 2>/dev/null; then
    nova_existente="${t#v}"
    nova_existente="${nova_existente%-hml}"
  fi
done

if git log -1 --format=%s | grep -qE '^chore: versiona [0-9]+\.[0-9]+\.[0-9]+ \('; then
  echo "Commit mais recente já é um bump de versão (evita loop) - nada a fazer."
  nova="$atual"
  echo "incrementou=false" >>"$GITHUB_OUTPUT"
elif [ -n "$nova_existente" ]; then
  nova="$nova_existente"
  echo "Tag $nova-hml já existe neste ciclo - reaproveitando alvo $nova"
else
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
      corpo=$(git log "$ultima_tag..HEAD" --format=%B || true)

      if echo "$corpo" | grep -qE '^[a-z]+(\([a-z0-9._/-]+\))?!:' || echo "$corpo" | grep -q 'BREAKING CHANGE'; then
        nivel="major"
      elif echo "$corpo" | grep -qE '^feat(\([a-z0-9._/-]+\))?:'; then
        nivel="minor"
      else
        nivel="patch"
      fi
      echo "Nivel detectado pelos commits desde $ultima_tag: $nivel"
    else
      # Nenhuma tag de producao ainda: nao houve primeiro release pra
      # incrementar a partir dele. "desde o inicio do historico" recontaria
      # o commit de breaking change original a CADA rodada (o `feat!:` que
      # criou o bot nunca some do log) - bumpando pra major sem parar mesmo
      # depois de uma correcao manual, porque nada marca esse commit como
      # "ja contabilizado". Mantem a versao atual do pyproject.toml (ja e' o
      # alvo do primeiro release) em vez de recalcular.
      nivel="none"
      echo "Nenhuma tag de producao ainda - mantendo a versao atual do pyproject.toml ($atual) como alvo do primeiro release."
    fi
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
    none)
      : # sem tag de producao ainda - versao fica como esta (ver comentario acima)
      ;;
    *)
      echo "::error::nivel invalido: '$nivel'"
      exit 1
      ;;
  esac

  nova="$major.$minor.$patch"

  if [ "$atual" = "$nova" ]; then
    echo "Versao ja esta correta ($atual), nada a fazer."
    echo "incrementou=false" >>"$GITHUB_OUTPUT"
  else
    sed "0,/^version = \"$atual\"/s//version = \"$nova\"/" "$PYPROJECT" >"$PYPROJECT.tmp"
    mv "$PYPROJECT.tmp" "$PYPROJECT"
    git add "$PYPROJECT"
    git commit -m "chore: versiona $nova (desde ${ultima_tag:-o início do histórico})"
    git push origin "HEAD:$BRANCH"
    echo "Versao atualizada: $atual -> $nova"
    echo "incrementou=true" >>"$GITHUB_OUTPUT"
  fi
fi

# Tag de homologacao: so em release/*, movel (sempre aponta pro commit mais
# novo dessa mesma release). fix/hotfix-* nao ganha - vai direto pra final.
if [[ "$BRANCH" == release/* ]]; then
  tag_hml="v${nova}-hml"
  git tag -f "$tag_hml" HEAD
  git push origin "refs/tags/$tag_hml" --force
  echo "Tag de homologação atualizada: $tag_hml -> $(git rev-parse --short HEAD)"

  if ! gh release view "$tag_hml" >/dev/null 2>&1; then
    gh release create "$tag_hml" --title "$tag_hml" --prerelease \
      --notes "Build de homologação da versão $nova, gerado a partir de $BRANCH."
    echo "Release de homologação criada: $tag_hml (pre-release)"
  fi
fi
