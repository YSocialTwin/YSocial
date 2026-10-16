# Revisione linguistica italiana (F5-2)

Chi revisiona: un madrelingua / referente di dominio. Esito richiesto per portare l'italiano da **beta** a **stable**
(`LANGUAGE_STATUS` in `y_web/i18n.py`, gate G5).

Come: impostare la lingua italiana (admin: profilo utente; simulazione: Impostazioni frontend dell'esperimento) e
percorrere le pagine sotto. Per ogni pagina annotare: testo non tradotto, traduzione errata o innaturale, termine
non conforme al glossario (`docs/i18n/glossary.csv`), testo troncato o che rompe il layout.
Le correzioni si fanno nei `.po` (core: `y_web/translations/it/LC_MESSAGES/messages.po`; plugin: `external/<plugin>/translations/it/...`),
poi `python scripts/i18n/catalogs.py compile`.

## Admin
- [ ] Login e registrazione
- [ ] Dashboard (esperimenti, client, conteggi con plurali)
- [ ] Creazione/modifica esperimento, impostazioni frontend (controlli lingua)
- [ ] Popolazioni e agenti, editor di agente
- [ ] Client e dettaglio client, log
- [ ] Analytics e annotazioni, opinioni
- [ ] Impostazioni, miscellanea, utenti, selettore lingua
- [ ] Tutorial/tour guidati
- [ ] Messaggi di errore e flash (validazioni)

## Simulazione (per piattaforma)
- [ ] Microblogging: home, profilo, hashtag, ricerca, messaggi, intervista
- [ ] Forum: community, thread, commenti
- [ ] Photo sharing: feed, storie, upload, profilo
- [ ] Pagine di errore (404/500)
- [ ] Selettore lingua del partecipante

## Plugin
- [ ] TrainingModules (corsi, esecuzioni, report, guida `docs/guide.it.md`)
- [ ] ScenarioDesign
- [ ] frontend_adds-on
- [ ] reactive_agents

Esito: ______ (approvato / correzioni da applicare)   Revisore: ______   Data: ______
