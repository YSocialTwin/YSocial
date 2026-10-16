# Fase 2: verifica finale

## Pseudo-locale `en-XA`

Con `python scripts/i18n/catalogs.py pseudo` (catalogo rigenerato: 2432 messaggi) e `PSEUDO_LOCALE_ENABLED=True`, le pagine admin (dashboard, experiments, populations, miscellanea, frontend_settings, users, user_details, agents) mostrano solo testo pseudo-localizzato, tranne:

- nomi delle lingue (`English`, `Italiano`: volutamente nativi);
- dati letti dal DB e non dai template: professioni, nazionalità, profili di attività, livelli di istruzione, orientamenti politici, interessi (pagine agents e populations);
- messaggi di stato scritti dai thread di sistema o salvati nel DB (es. "Detoxify model is ready.", `Ready`, notifiche), che non hanno un contesto di richiesta al momento della creazione.

Questi tre gruppi sono limiti noti: richiedono una mappa di etichette per i dati e una traduzione lazy dei messaggi salvati. Non sono stati inclusi nella Fase 2.

## Revisione dell'italiano

Terminologia coerente su tutto il catalogo (esperimento, popolazione, agente, simulazione, configurazione/impostazioni, elimina, salva; "client" resta invariato). 0 stringhe non tradotte, 0 fuzzy; le 17 voci identiche all'inglese sono nomi propri, URL o codice.
