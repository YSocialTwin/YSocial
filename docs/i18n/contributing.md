# Tradurre e mantenere YSocial: guida per contributori (Fase 6)

Lingue: inglese (sorgente) e italiano. Convenzioni tecniche in `conventions.md`, termini in `glossary.csv`.

## Aggiungere o cambiare un testo
1. Marca la stringa: `_()` / `N_()` in Python e Jinja, `YI18n.t('English text', {k: v})` in JS. Mai concatenare frasi, mai passare testi utente (post, commenti, agenti) dai cataloghi.
2. `python scripts/i18n/catalogs.py update`, traduci i nuovi `msgid` vuoti in `y_web/translations/it/LC_MESSAGES/messages.po`
   (plugin: `python scripts/i18n/plugin_catalogs.py`; JS: `python scripts/i18n/jscatalog.py sync`).
3. `python scripts/i18n/catalogs.py compile` e committa `.po` **e** `.mo`.
4. Controlli locali, gli stessi della CI: `catalogs.py check`, `scan_unmarked.py --check`, `check_glossary.py`, `coverage_report.py --min 98`.

## Revisione
Ogni PR che cambia testi visibili aggiorna l'italiano. Le correzioni linguistiche seguono `review-checklist.md`; il glossario si modifica solo con approvazione del referente.

## Rilascio di una lingua
- **beta**: copertura < 98% o revisione madrelingua non completata. Il selettore mostra "(beta)" (`LANGUAGE_STATUS` in `y_web/i18n.py`).
- **stable**: copertura >= 98%, glossario a 0 violazioni, revisione completata e G4 (esperimento reale per piattaforma) superato. Si promuove rimuovendo la lingua da `LANGUAGE_STATUS`.
- Note di rilascio: elencare lingue nuove/promosse e plugin con catalogo aggiornato; i `.mo` dei plugin vanno committati con il plugin.

## Kill switch
`YSOCIAL_LANGUAGES=en` (variabile d'ambiente, riavvio dell'app) ritira tutte le lingue tranne l'inglese: i selettori spariscono e le lingue salvate (utente, esperimento) ricadono sull'inglese. Esempio di ripristino: `YSOCIAL_LANGUAGES=en,it`.

## Nuova lingua
Guida completa (UI, plugin, prompt, memoria, controlli, rilascio) in inglese: [adding-a-language.md](adding-a-language.md). Richiede comunque una decisione esplicita dei referenti.
