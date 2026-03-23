#!/usr/bin/env bash
# audit_templates.sh
#
# Measures the current state of HTML/CSS/JS mixing inside y_web/templates/.
# Run from the repository root:
#
#   bash scripts/audit_templates.sh
#
# Output is printed to stdout in a machine-readable key=value format so it
# can be captured into docs/template_audit_baseline.txt for phase-over-phase
# comparison:
#
#   bash scripts/audit_templates.sh > docs/template_audit_baseline.txt
#
# See TEMPLATE_SEPARATION_REFACTORING.md, Phase T1 for full context.

set -uo pipefail

ROOT="y_web/templates"

if [ ! -d "$ROOT" ]; then
  echo "ERROR: '$ROOT' directory not found. Run this script from the repository root." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
count_in_dir() {
  # count_in_dir <dir> <pattern> [--perl]
  # Count matching lines in all .html files directly inside <dir> (non-recursive).
  local dir="$1"
  local pattern="$2"
  local perl="${3:-}"
  local files
  # Build a list of .html files in this directory only (not recursive)
  mapfile -t files < <(find "$dir" -maxdepth 1 -name "*.html" 2>/dev/null)
  if [ "${#files[@]}" -eq 0 ]; then
    echo 0
    return 0
  fi
  if [ "$perl" = "--perl" ]; then
    grep -cP "$pattern" "${files[@]}" 2>/dev/null \
      | awk -F: '$2>0{sum+=$2} END{print sum+0}'
  else
    grep -c "$pattern" "${files[@]}" 2>/dev/null \
      | awk -F: '$2>0{sum+=$2} END{print sum+0}'
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Overall totals
# ---------------------------------------------------------------------------
echo "# Template CSS/JS Audit"
echo "# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "# Repository root: $(pwd)"
echo ""

echo "## Overall Totals"
echo ""

FILES_WITH_STYLE_BLOCKS=$(grep -r '<style>' "$ROOT" --include="*.html" -l | wc -l | tr -d ' ')
TOTAL_STYLE_BLOCKS=$(grep -r '<style>' "$ROOT" --include="*.html" | wc -l | tr -d ' ')
TOTAL_STYLE_ATTRS=$(grep -r 'style=' "$ROOT" --include="*.html" | wc -l | tr -d ' ')
TOTAL_INLINE_SCRIPTS=$(grep -rP '<script(?![^>]*src)>' "$ROOT" --include="*.html" | wc -l | tr -d ' ')
TOTAL_BROWSERSYNC=$(grep -r '__bs_script__' "$ROOT" --include="*.html" | wc -l | tr -d ' ')
TOTAL_HTML_FILES=$(find "$ROOT" -name "*.html" | wc -l | tr -d ' ')
TOTAL_LINES=$(find "$ROOT" -name "*.html" | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')

echo "files_with_style_blocks=$FILES_WITH_STYLE_BLOCKS"
echo "total_style_blocks=$TOTAL_STYLE_BLOCKS"
echo "total_style_attrs=$TOTAL_STYLE_ATTRS"
echo "total_inline_scripts=$TOTAL_INLINE_SCRIPTS"
echo "total_browsersync_occurrences=$TOTAL_BROWSERSYNC"
echo "total_html_files=$TOTAL_HTML_FILES"
echo "total_lines=$TOTAL_LINES"
echo ""

# ---------------------------------------------------------------------------
# Per-section breakdown
# ---------------------------------------------------------------------------
echo "## Per-Section Breakdown"
echo ""
echo "# section : html_files | style_blocks | style_attrs | inline_scripts"
echo ""

for SECTION in \
    "admin" \
    "admin/tutorials" \
    "error_pages" \
    "forum" \
    "forum/components" \
    "login" \
    "microblogging" \
    "microblogging/components"; do

  DIR="$ROOT/$SECTION"
  if [ ! -d "$DIR" ]; then
    continue
  fi

  SECT_FILES=$(find "$DIR" -maxdepth 1 -name "*.html" | wc -l | tr -d ' ')
  SECT_STYLE_BLOCKS=$(count_in_dir "$DIR" '<style>')
  SECT_STYLE_ATTRS=$(count_in_dir "$DIR" 'style=')
  SECT_INLINE_SCRIPTS=$(count_in_dir "$DIR" '<script(?![^>]*src)>' --perl)

  # Normalise section name to a variable-safe key
  KEY=$(echo "$SECTION" | tr '/' '_')
  echo "section_${KEY}_files=$SECT_FILES"
  echo "section_${KEY}_style_blocks=$SECT_STYLE_BLOCKS"
  echo "section_${KEY}_style_attrs=$SECT_STYLE_ATTRS"
  echo "section_${KEY}_inline_scripts=$SECT_INLINE_SCRIPTS"
  echo ""
done

# ---------------------------------------------------------------------------
# Top offenders — style= attribute density
# ---------------------------------------------------------------------------
echo "## Top 10 Files by style= Attribute Count"
echo ""
find "$ROOT" -name "*.html" | \
  xargs grep -c 'style=' 2>/dev/null | \
  sort -t: -k2 -nr | \
  head -10 | \
  while IFS=: read -r path cnt; do
    rel="${path#$ROOT/}"
    echo "style_attrs_top: $cnt  $rel"
  done || true
echo ""

# ---------------------------------------------------------------------------
# Top offenders — inline <script> density
# ---------------------------------------------------------------------------
echo "## Top 10 Files by Inline <script> Block Count"
echo ""
find "$ROOT" -name "*.html" | \
  xargs grep -cP '<script(?![^>]*src)>' 2>/dev/null | \
  sort -t: -k2 -nr | \
  head -10 | \
  while IFS=: read -r path cnt; do
    rel="${path#$ROOT/}"
    echo "inline_scripts_top: $cnt  $rel"
  done || true
echo ""

# ---------------------------------------------------------------------------
# Files with <style> blocks
# ---------------------------------------------------------------------------
echo "## Files Containing Inline <style> Blocks"
echo ""
grep -r '<style>' "$ROOT" --include="*.html" -l | \
  sort | \
  while read -r path; do
    rel="${path#$ROOT/}"
    cnt=$(grep -c '<style>' "$path")
    echo "has_style_block: $cnt  $rel"
  done || true
echo ""

# ---------------------------------------------------------------------------
# BrowserSync occurrences
# ---------------------------------------------------------------------------
echo "## Files Containing BrowserSync Snippet"
echo ""
grep -r '__bs_script__' "$ROOT" --include="*.html" -l | \
  sort | \
  while read -r path; do
    rel="${path#$ROOT/}"
    echo "has_browsersync: $rel"
  done || true
echo ""

echo "# End of audit"
