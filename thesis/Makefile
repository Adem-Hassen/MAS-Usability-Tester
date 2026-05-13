# ============================================================================
# VerSimUX Thesis — Build Automation
# ============================================================================
# Usage:
#   make          — Full build (pdf)
#   make pdf      — Compile thesis to PDF
#   make clean    — Remove all generated files
#   make watch    — Continuous compilation (requires latexmk)
#   make wc       — Word count estimate
# ============================================================================

MAIN = main
LATEX = pdflatex
BIBER = biber
LATEXMK = latexmk

# Full build with bibliography
.PHONY: pdf
pdf:
	$(LATEXMK) -pdf -interaction=nonstopmode $(MAIN).tex

# Quick build (no bibliography update)
.PHONY: quick
quick:
	$(LATEX) -interaction=nonstopmode $(MAIN).tex

# Continuous compilation (auto-rebuild on save)
.PHONY: watch
watch:
	$(LATEXMK) -pdf -pvc -interaction=nonstopmode $(MAIN).tex

# Clean generated files
.PHONY: clean
clean:
	$(LATEXMK) -C
	rm -f *.bbl *.blg *.run.xml *.bcf
	rm -f *.glg *.glo *.gls *.ist
	rm -f *.lol  # list of listings
	rm -f chapters/*.aux appendices/*.aux frontmatter/*.aux

# Word count (approximate)
.PHONY: wc
wc:
	@echo "=== Approximate word count ==="
	@texcount -inc -merge $(MAIN).tex 2>/dev/null || \
		echo "Install texcount: tlmgr install texcount"

# Default target
.DEFAULT_GOAL := pdf
