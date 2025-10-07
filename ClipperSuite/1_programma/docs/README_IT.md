# ClipperStudio

ClipperStudio è un'applicazione desktop scritta in Python 3 che automatizza il
workflow necessario per trasformare video lunghi in clip verticali perfette per
TikTok, Shorts e Reels. L'interfaccia grafica è realizzata con Tkinter ed è
pensata per gestire più account contemporaneamente grazie alle schede
(indipendenti) nella parte inferiore della finestra.

## Caratteristiche principali

* **Suddivisione automatica**: ogni video viene tagliato in clip da circa 2
  minuti. L'ultima clip viene regolata automaticamente per durare fra 2 e 4
  minuti così da evitare spezzoni troppo brevi.
* **Formato verticale 9:16**: il video viene convertito in verticale con sfondo
  sfocato e sovrapposizioni testuali opzionali (titolo e "Parte N").
* **Sottotitoli Whisper**: se la libreria `whisper` è installata viene generato
  automaticamente un file SRT che può essere bruciato nel video.
* **Pubblicazione seriale**: download, elaborazione e upload avvengono in modo
  strettamente sequenziale per minimizzare l'utilizzo di spazio disco.
* **Pulizia automatica**: i file sorgente vengono cancellati dopo il rendering,
  mentre le clip vengono rimosse solo dopo la pubblicazione.
* **Intervallo dinamico**: è possibile impostare un intervallo base (in
  minuti) tra una clip e la successiva. Con il nuovo pulsante "Random delay" si
  può attivare una randomizzazione uniforme ±2 minuti (o un valore personalizzabile)
  per evitare pattern di pubblicazione troppo regolari.
* **Gestione multi-account**: ogni scheda mantiene token, impostazioni e coda
  indipendenti; le code vengono lavorate in parallelo ma ogni scheda rimane
  seriale internamente.

## Dipendenze opzionali

ClipperStudio sfrutta strumenti esterni per le operazioni più pesanti. Installa
questi componenti per ottenere tutte le funzionalità:

* [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) per il download dei video.
* [`ffmpeg`](https://ffmpeg.org/) e `ffprobe` per il rendering e l'estrazione di
  informazioni dal media.
* [`whisper`](https://github.com/openai/whisper) per la trascrizione automatica.

Il programma verifica la presenza dei binari necessari e mostra un errore
informativo se uno di essi manca.

## Avvio

```bash
python ClipperSuite/1_programma/ClipperStudio_GUI.py
```

La finestra principale si aprirà immediatamente senza necessità di interazione
con il terminale. Inserisci i link (uno per riga), configura l'intervallo base
fra le clip e premi "Aggiungi alla coda" per avviare il processo.

## Struttura del progetto

```
ClipperSuite/
├── 1_programma/
│   ├── ClipperStudio_GUI.py          # Interfaccia grafica principale
│   ├── clipperstudio/                # Moduli condivisi (config, pipeline, ecc.)
│   ├── config/
│   │   └── settings.json             # Creato automaticamente con i valori base
│   └── docs/
│       └── README_IT.md              # Questo documento
├── 2_spaziatura/                     # Workspace generati al volo (downloads, clips...)
└── 3_programmi_necessari/            # Binari opzionali (ffmpeg, yt-dlp, ambiente Python)
```

## Note sullo spazio disco

Il sistema implementa la strategia descritta nel brief originale: ogni video
viene scaricato, elaborato e pubblicato prima di passare al successivo. I file
sorgente vengono eliminati appena non sono più necessari e le clip vengono
cancellate solo dopo una pubblicazione completata con successo.
