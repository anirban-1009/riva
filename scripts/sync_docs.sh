#!/usr/bin/env bash
# ==============================================================================
# Riva Documentation Sync: Keep docs/ and wiki/ in lockstep
# ==============================================================================
# Dynamic Naming Convention:
#   docs/ -> lowercase kebab-case (e.g. "product-definition.md")
#   wiki/ -> Title-Hyphen-Case (e.g. "Product-Definition.md")
#   Acronyms preserved in uppercase: MLX, NLP, LLM, PR, API, CLI, SSE, AI, UI.
#   Special wiki pages (_Sidebar.md, _Footer.md, _Header.md, Home.md) are excluded.
#
# Usage:
#   ./scripts/sync_docs.sh [status|wiki-to-docs|docs-to-wiki|diff]
#
# Commands:
#   status (default)  Checks for drift between docs/ and wiki/
#   wiki-to-docs      Copies from canonical wiki/ to in-repo docs/ (adds mirror badge)
#   docs-to-wiki      Copies from in-repo docs/ to wiki/ (strips mirror badge)
#   diff [file]       Shows unified diff between docs/ and wiki/ for drifted files
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCS_DIR="${REPO_ROOT}/docs"
WIKI_DIR="${REPO_ROOT}/wiki"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✔${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✖${NC} $1"; }

# ------------------------------------------------------------------------------
# Dynamic Naming Convention & Discovery
# ------------------------------------------------------------------------------
# Discovers all .md files in docs/ and wiki/ dynamically, pairing them via
# standard kebab-case <-> Title-Case convention. Zero hardcoded list needed.
get_mappings() {
    python3 - "${DOCS_DIR}" "${WIKI_DIR}" << 'EOF'
import sys, os, glob

docs_dir, wiki_dir = sys.argv[1], sys.argv[2]
exclude_wiki = {"_Sidebar.md", "_Footer.md", "_Header.md", "Home.md"}
acronyms = {
    "mlx": "MLX", "nlp": "NLP", "llm": "LLM", "pr": "PR",
    "api": "API", "cli": "CLI", "sse": "SSE", "ai": "AI", "ui": "UI"
}

# Aliases for historical non-standard or abbreviated names
aliases = {
    "nlp-memory-routing.md": "NLP-Memory-Routing-Learnings-and-Pitfalls.md",
}

def doc_to_wiki(name):
    if name in aliases:
        return aliases[name]
    stem = name.removesuffix(".md").replace("_", "-")
    words = stem.split("-")
    wiki_words = [acronyms.get(w.lower(), w.capitalize()) for w in words]
    return "-".join(wiki_words) + ".md"

def wiki_to_doc(name):
    for d, w in aliases.items():
        if w.lower() == name.lower():
            return d
    stem = name.removesuffix(".md")
    return stem.lower().replace("_", "-") + ".md"

docs_files = {os.path.basename(f) for f in glob.glob(f"{docs_dir}/*.md")}
wiki_files = {os.path.basename(f) for f in glob.glob(f"{wiki_dir}/*.md") if os.path.basename(f) not in exclude_wiki}

pairs = {}
for d in docs_files:
    pairs[d] = doc_to_wiki(d)

for w in wiki_files:
    d = wiki_to_doc(w)
    if d not in pairs:
        pairs[d] = w

for d, w in sorted(pairs.items()):
    print(f"{d}:{w}")
EOF
}

# Strip the "> Mirrors the [wiki]..." notice block from a file's content
strip_mirror_notice() {
    local file="$1"
    awk '
        BEGIN { in_notice=0 }
        /^> Mirrors the \[wiki\]/ { in_notice=1; next }
        in_notice && /^$/ { in_notice=0; next }
        !in_notice { print }
    ' "${file}"
}

# Generate docs file from wiki file with proper mirror notice
render_docs_file() {
    local wiki_path="$1"
    local wiki_filename="$2"
    local wiki_slug="${wiki_filename%.md}"

    awk -v slug="${wiki_slug}" '
        NR==1 && /^# / {
            print $0
            print ""
            print "> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/" slug ") — the wiki is the canonical source; update it first."
            next
        }
        { print }
    ' "${wiki_path}"
}

# ------------------------------------------------------------------------------
# Action: Status
# ------------------------------------------------------------------------------
cmd_status() {
    echo -e "${BOLD}--- Riva Documentation Sync Status (Dynamic Convention) ---${NC}"
    printf "%-35s %-45s %-12s\n" "docs/ (kebab-case)" "wiki/ (Title-Case)" "Status"
    printf "%-35s %-45s %-12s\n" "-----------------------------------" "---------------------------------------------" "------------"

    local drifted=0
    local in_sync=0
    local missing=0

    while IFS=':' read -r doc_file wiki_file; do
        [[ -z "${doc_file}" ]] && continue

        local doc_path="${DOCS_DIR}/${doc_file}"
        local wiki_path="${WIKI_DIR}/${wiki_file}"

        if [[ ! -f "${doc_path}" && ! -f "${wiki_path}" ]]; then
            printf "%-35s %-45s ${RED}%-12s${NC}\n" "${doc_file}" "${wiki_file}" "BOTH MISSING"
            missing=$((missing + 1))
        elif [[ ! -f "${doc_path}" ]]; then
            printf "%-35s %-45s ${YELLOW}%-12s${NC}\n" "MISSING" "${wiki_file}" "WIKI ONLY"
            drifted=$((drifted + 1))
        elif [[ ! -f "${wiki_path}" ]]; then
            printf "%-35s %-45s ${YELLOW}%-12s${NC}\n" "${doc_file}" "MISSING" "DOCS ONLY"
            drifted=$((drifted + 1))
        else
            # Compare normalized content (without mirror notice)
            local clean_doc clean_wiki
            clean_doc=$(strip_mirror_notice "${doc_path}")
            clean_wiki=$(cat "${wiki_path}")

            if diff -q <(echo "${clean_doc}") <(echo "${clean_wiki}") >/dev/null 2>&1; then
                printf "%-35s %-45s ${GREEN}%-12s${NC}\n" "${doc_file}" "${wiki_file}" "IN SYNC"
                in_sync=$((in_sync + 1))
            else
                printf "%-35s %-45s ${RED}%-12s${NC}\n" "${doc_file}" "${wiki_file}" "DRIFTED"
                drifted=$((drifted + 1))
            fi
        fi
    done < <(get_mappings)

    echo -e "--------------------------------------------------------------------------------------------------"
    echo -e "Summary: ${GREEN}${in_sync} in sync${NC}, ${YELLOW}${drifted} drifted/one-sided${NC}, ${RED}${missing} missing${NC}"

    if [[ ${drifted} -gt 0 ]]; then
        echo ""
        echo -e "To resolve drift:"
        echo -e "  • Overwrite docs/ with wiki/ versions:  ${BOLD}./scripts/sync_docs.sh wiki-to-docs${NC}"
        echo -e "  • Overwrite wiki/ with docs/ versions:  ${BOLD}./scripts/sync_docs.sh docs-to-wiki${NC}"
        echo -e "  • Inspect diff for a file:              ${BOLD}./scripts/sync_docs.sh diff <filename>${NC}"
    fi
}

# ------------------------------------------------------------------------------
# Action: Diff
# ------------------------------------------------------------------------------
cmd_diff() {
    local target="$1"
    local found=0

    while IFS=':' read -r doc_file wiki_file; do
        [[ -z "${doc_file}" ]] && continue

        if [[ -n "${target}" && "${doc_file}" != *"${target}"* && "${wiki_file}" != *"${target}"* ]]; then
            continue
        fi

        local doc_path="${DOCS_DIR}/${doc_file}"
        local wiki_path="${WIKI_DIR}/${wiki_file}"

        if [[ -f "${doc_path}" && -f "${wiki_path}" ]]; then
            local clean_doc clean_wiki
            clean_doc=$(strip_mirror_notice "${doc_path}")
            clean_wiki=$(cat "${wiki_path}")

            if ! diff -u <(echo "${clean_doc}") <(echo "${clean_wiki}") >/dev/null 2>&1; then
                found=$((found + 1))
                echo -e "${BOLD}=== Diff: docs/${doc_file} <-> wiki/${wiki_file} ===${NC}"
                diff -u --color=always \
                    --label "docs/${doc_file} (without mirror notice)" <(echo "${clean_doc}") \
                    --label "wiki/${wiki_file}" <(echo "${clean_wiki}") || true
                echo ""
            fi
        fi
    done < <(get_mappings)

    if [[ ${found} -eq 0 ]]; then
        log_success "No differences found between mapped docs and wiki files."
    fi
}

# ------------------------------------------------------------------------------
# Action: Wiki -> Docs
# ------------------------------------------------------------------------------
cmd_wiki_to_docs() {
    log_info "Syncing canonical wiki/ files -> docs/ (using naming convention)..."
    mkdir -p "${DOCS_DIR}"

    while IFS=':' read -r doc_file wiki_file; do
        [[ -z "${doc_file}" ]] && continue

        local doc_path="${DOCS_DIR}/${doc_file}"
        local wiki_path="${WIKI_DIR}/${wiki_file}"

        if [[ -f "${wiki_path}" ]]; then
            render_docs_file "${wiki_path}" "${wiki_file}" > "${doc_path}"
            log_success "Synced wiki/${wiki_file} -> docs/${doc_file}"
        else
            log_warn "wiki/${wiki_file} not found; skipping."
        fi
    done < <(get_mappings)

    echo ""
    log_success "docs/ has been refreshed from wiki/."
}

# ------------------------------------------------------------------------------
# Action: Docs -> Wiki
# ------------------------------------------------------------------------------
cmd_docs_to_wiki() {
    log_info "Syncing docs/ files -> wiki/ (using naming convention)..."
    mkdir -p "${WIKI_DIR}"

    while IFS=':' read -r doc_file wiki_file; do
        [[ -z "${doc_file}" ]] && continue

        local doc_path="${DOCS_DIR}/${doc_file}"
        local wiki_path="${WIKI_DIR}/${wiki_file}"

        if [[ -f "${doc_path}" ]]; then
            strip_mirror_notice "${doc_path}" > "${wiki_path}"
            log_success "Synced docs/${doc_file} -> wiki/${wiki_file}"
        else
            log_warn "docs/${doc_file} not found; skipping."
        fi
    done < <(get_mappings)

    echo ""
    log_success "wiki/ has been refreshed from docs/."
    log_info "Remember to review and commit changes in wiki/ submodule if you want to push to the wiki remote."
}

# ------------------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------------------
cmd="${1:-status}"
shift || true

case "${cmd}" in
    status|check)
        cmd_status
        ;;
    diff)
        cmd_diff "$@"
        ;;
    wiki-to-docs|pull|w2d)
        cmd_wiki_to_docs
        ;;
    docs-to-wiki|push|d2w)
        cmd_docs_to_wiki
        ;;
    help|--help|-h)
        sed -n '2,17p' "$0" | tr -d '#'
        ;;
    *)
        log_error "Unknown command: ${cmd}"
        echo "Usage: $0 {status|diff|wiki-to-docs|docs-to-wiki}"
        exit 1
        ;;
esac
