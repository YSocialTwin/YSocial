// Launcher translations (English is the source language; Italian mirrors the app's it catalog tone).
// Add a language: add a key to DICT, then to the <select id="lang"> in index.html.
window.LAUNCHER_I18N = (function () {
  const DICT = {
    en: {},
    it: {
      "setup.title": "Prepariamo tutto",
      "setup.sub": "Un social network digitale popolato da agenti intelligenti: osserva, sperimenta e scopri come nascono le conversazioni.",
      "setup.home": "Dove conservare i dati",
      "setup.install": "Installa YSocial",
      "setup.adv": "Opzioni avanzate",
      "inst.title": "Preparazione in corso…",
      "inst.sub": "La prima volta richiede qualche minuto. Puoi lasciare aperta questa finestra.",
      "inst.python": "Preparazione di Python",
      "inst.env": "Creazione di un ambiente privato",
      "inst.app": "Installazione di YSocial",
      "ready.title": "Pronto quando vuoi",
      "ready.sub": "YSocial è installato. Avvialo quando vuoi.",
      "ready.title.run": "YSocial è in esecuzione",
      "ready.sub.run": "Puoi chiudere questa finestra: YSocial resta attivo finché non lo fermi.",
      "status.stopped": "Fermo",
      "status.running": "In esecuzione su http://{host}:{port}",
      "btn.start": "Avvia YSocial",
      "btn.starting": "Avvio in corso… può richiedere un minuto",
      "btn.running": "YSocial è in esecuzione",
      "btn.stop": "Ferma YSocial",
      "ready.data": "Dati:",
      "ready.reinstall": "Reinstalla",
      "ready.uninstall": "Disinstalla",
      "un.title": "Disinstallare YSocial?",
      "un.sub": "Il programma viene rimosso da questo computer. Esperimenti e dati restano, a meno che tu non spunti una casella qui sotto.",
      "un.data": "Elimina anche i miei dati",
      "un.data.desc": "Esperimenti, database e impostazioni nella cartella dei dati. L'operazione non è reversibile.",
      "un.confirm": "Disinstalla",
      "un.cancel": "Annulla",
      "more": "Altre opzioni",
      "opt.window": "Apri in una finestra dedicata",
      "opt.window.desc": "Deseleziona per usare il browser predefinito.",
      "opt.threaded": "Servi le richieste in parallelo",
      "opt.threaded.desc": "Mantiene l'interfaccia reattiva mentre YSocial è occupato. Deseleziona per gestire una richiesta alla volta. Vale dal prossimo avvio.",
      "opt.host": "Indirizzo",
      "opt.port": "Porta",
      "opt.hostnote": "Usa <code>0.0.0.0</code> come indirizzo solo se vuoi che altri computer della rete raggiungano YSocial.",
      "opt.jupyter": "Avvia il server Jupyter Notebook",
      "release": "Release",
      "upd.launcher": "È disponibile anche un nuovo installatore: apri la pagina della release",
      "tox.add.title": "Rilevamento della tossicità",
      "tox.add.desc": "Facoltativo, serve solo se gli esperimenti valutano contenuti tossici. Download molto grande (PyTorch, diversi GB di spazio su disco).",
      "tox.add.btn": "Aggiungi",
      "tox.adding": "Aggiunta del rilevamento della tossicità…",
      "tox.adding.sub": "Download molto grande: può richiedere diversi minuti.",
      "un.models": "Elimina anche i modelli di tossicità",
      "un.models.desc": "Modelli linguistici scaricati, conservati fuori dalla cartella dei dati:",
      "ver.label": "Versione",
      "upd.avail": "È disponibile YSocial {v}",
      "upd.btn": "Aggiorna",
      "upd.title": "Aggiornamento in corso…",
      "upd.sub": "Aggiornamento di YSocial in corso. I tuoi dati non vengono toccati.",
      "upd.done": "Aggiornato alla versione {v}",
      "opt.updates": "Controlla gli aggiornamenti",
      "opt.updates.desc": "Cerca nuove versioni di YSocial all'apertura del launcher.",
      "err.space": "Spazio su disco insufficiente. Libera spazio e riprova.",
      "err.net": "Impossibile scaricare quanto necessario. Controlla la connessione a internet e riprova.",
      "err.foreign": "YSocial è già in esecuzione, ma non è stato avviato da questo launcher (per esempio da un terminale). Chiudi quella finestra del terminale o termina quel processo, poi riprova.",
      "err.port": "Quella porta è già in uso. Sceglierne un'altra in Altre opzioni.",
      "err.other": "Qualcosa è andato storto: {msg}"
    }
  };
  const pick = () => {
    let saved = null;
    try { saved = localStorage.getItem("ysocial.lang"); } catch (_) {}
    const l = saved && saved !== "auto" ? saved : (navigator.language || "en").slice(0, 2).toLowerCase();
    return DICT[l] ? l : "en";
  };
  let lang = pick();
  const t = (key, fallback, vars) => {
    let s = (DICT[lang] && DICT[lang][key]) || fallback;
    if (vars) for (const k in vars) s = s.replace("{" + k + "}", vars[k]);
    return s;
  };
  const apply = () => {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      if (!el.dataset.en) el.dataset.en = el.innerHTML;
      el.innerHTML = t(el.dataset.i18n, el.dataset.en);
    });
  };
  return {
    t, apply,
    get lang() { return lang; },
    set: (l) => {
      try { localStorage.setItem("ysocial.lang", l); } catch (_) {}
      lang = pick(); apply();
    },
    saved: () => { try { return localStorage.getItem("ysocial.lang") || "auto"; } catch (_) { return "auto"; } },
  };
})();
