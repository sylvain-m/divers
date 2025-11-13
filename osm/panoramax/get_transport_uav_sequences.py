name: Export Panoramax UAV Sequences

on:
  schedule:
    # Tous les jours à 00h30 UTC (01h30/02h30 en France)
    - cron: '30 0 * * *'
  workflow_dispatch:  # Permet de lancer manuellement

jobs:
  export:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configurer Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Installer les dépendances
        run: pip install requests
      - name: Exécuter le script
        run: python osm/panoramax/get_transport_uav_sequences.py
      - name: Valider et pousser les changements
        run: |
          git config --global user.name "sylvain-m"
          git config --global user.email "sylvain.montagner@free.fr"
          git add osm/panoramax/panoramax_osm_transport_uav_sequences.geojson
          git commit -m "Mise à jour automatique du fichier Panoramax UAV sequences"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
