import logging
import os
import xml.etree.ElementTree as ET
import ftplib
import tkinter as tk
import threading
import time
import shutil
import pysftp  

# === CONFIGURATION DES LOGS ===
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# === CHARGEMENT DES CLIENTS ===
def charger_clients(fichier):
    """Charge les informations des clients FTP depuis le fichier XML."""
    try:
        tree = ET.parse(fichier)
        root = tree.getroot()
        clients = []
        for client in root.findall('client'):
            info = {
                'nom': client.find('nom').text if client.find('nom') is not None else "Inconnu",
                'protocol': client.find('FTP/protocol').text if client.find('FTP/protocol') is not None else "FTP",
                'adresse': client.find('FTP/adresse').text if client.find('FTP/adresse') is not None else "",
                'port': int(client.find('FTP/port').text) if client.find('FTP/port') is not None else 21,
                'user': client.find('FTP/user').text if client.find('FTP/user') is not None else "",
                'password': client.find('FTP/password').text if client.find('FTP/password') is not None else "",
                'dossier': client.find('FTP/dossier').text.replace('\\', '/') if client.find('FTP/dossier') is not None else "/",
                'Rep_travail': client.find('Rep_travail').text.replace('\\', '/') if client.find('Rep_travail') is not None else "reception",
                'Fic_NAV': client.find('Fic_NAV').text if client.find('Fic_NAV') is not None else None,
                'extension': client.find('extension').text if client.find('extension') is not None else None,
                'encodage': client.find('encodage').text if client.find('encodage') is not None else None,
            }
            clients.append(info)
        logging.info(f"Chargé {len(clients)} clients depuis {fichier}.")
        return clients
    except Exception as e:
        logging.error(f"Erreur lors du chargement du fichier XML : {e}")
        return []

# === FONCTION POUR METTRE À JOUR LA COULEUR D'UNE CASE ===
def maj_couleur(client_nom, colonne, couleur):
    """Met à jour la couleur d'une cellule pour un client."""
    try:
        widget = client_widgets[client_nom][colonne]
        widget.after(0, lambda: widget.config(bg=couleur))
    except Exception as e:
        logging.error(f"Erreur maj couleur pour {client_nom}/{colonne} : {e}")

# === TRAITEMENT LOCAL ===
def renommer_et_encoder(client, local_file):
    """Renomme et encode le fichier si nécessaire."""
    try:
        Fic_NAV = client.get('Fic_NAV')
        extension = client.get('extension')
        encodage = client.get('encodage')
        dossier_dest = client.get('Rep_travail')

        nouveau_nom = Fic_NAV if Fic_NAV else os.path.basename(local_file)
        if extension and not nouveau_nom.endswith(extension):
            nouveau_nom = f"{os.path.splitext(nouveau_nom)[0]}{extension}"

        fichier_destination = os.path.join(dossier_dest, nouveau_nom)

        while os.path.exists(fichier_destination):
            logging.warning(f"Le fichier {fichier_destination} existe déjà. En attente...")
            time.sleep(5)

        if encodage and encodage.lower() != "binary":
            with open(local_file, 'r', encoding='utf-8') as source:
                contenu = source.read()
            with open(fichier_destination, 'w', encoding=encodage) as target:
                target.write(contenu)
            os.remove(local_file)
            logging.info(f"Fichier encodé et déplacé : {fichier_destination}")
        else:
            shutil.move(local_file, fichier_destination)
            logging.info(f"Fichier déplacé : {fichier_destination}")

        return nouveau_nom
    except Exception as e:
        logging.error(f"Erreur lors du traitement du fichier {local_file} : {e}")
        return None

def supprimer_fichier_source(chemin_fichier):
    try:
        os.remove(chemin_fichier)
        logging.info(f"Fichier {chemin_fichier} supprimé.")
    except Exception as e:
        logging.error(f"Erreur lors de la suppression de {chemin_fichier} : {e}")

def traiter_fichiers_localement(client, chemin):
    if os.path.exists(chemin):
        fichiers = os.listdir(chemin)
        for fichier in fichiers:
            fichier_source = os.path.join(chemin, fichier)
            try:
                nom_final = renommer_et_encoder(client, fichier_source)
                if nom_final and os.path.exists(fichier_source):
                    supprimer_fichier_source(fichier_source)
            except Exception as e:
                logging.error(f"Erreur lors du traitement local de {fichier_source} : {e}")
    else:
        logging.error(f"Chemin introuvable : {chemin}")

# === TRANSFERT DES FICHIERS AVEC PYSFTP (Dans ce cas PYSFTP est utilisé car il a fallu adapté avec la version de l'utilisateur) ===
def transferer_fichiers(client):
    try:
        maj_couleur(client['nom'], "Connexion", "yellow")

        if client['protocol'] == 'SFTP':
            try:
                cnopts = pysftp.CnOpts()
                cnopts.hostkeys = None  
                with pysftp.Connection(
                    host=client['adresse'],
                    username=client['user'],
                    password=client['password'],
                    port=client['port'],
                    cnopts=cnopts
                ) as sftp:

                    maj_couleur(client['nom'], "Connexion", "green")
                    dossier_source = client['dossier']
                    dossier_dest = client['Rep_travail']

                    if not sftp.exists(dossier_source):
                        logging.error(f"Dossier source introuvable : {dossier_source}")
                        maj_couleur(client['nom'], "FTP", "red")
                        return

                    fichiers = sftp.listdir(dossier_source)
                    if not fichiers:
                        maj_couleur(client['nom'], "FTP", "green")
                        return

                    for fichier in fichiers:
                        try:
                            maj_couleur(client['nom'], "FTP", "yellow")
                            remote_path = f"{dossier_source}/{fichier}"
                            local_path = os.path.join(dossier_dest, fichier)
                            sftp.get(remote_path, local_path)
                            nom_final = renommer_et_encoder(client, local_path)
                            if nom_final:
                                sftp.remove(remote_path)
                                maj_couleur(client['nom'], "FTP", "green")
                                logging.info(f"Fichier {fichier} traité et supprimé du serveur.")
                            else:
                                maj_couleur(client['nom'], "FTP", "red")
                        except Exception as e:
                            logging.error(f"Erreur transfert {fichier} : {e}")
                            maj_couleur(client['nom'], "FTP", "red")

            except Exception as e:
                logging.error(f"Erreur de connexion SFTP pour {client['nom']} : {e}")
                maj_couleur(client['nom'], "Connexion", "red")

        elif client['protocol'] == 'FTP':
            with ftplib.FTP(client['adresse'], client['user'], client['password']) as ftp:
                maj_couleur(client['nom'], "Connexion", "green")
                ftp.cwd(client['dossier'])
                fichiers = ftp.nlst()
                for fichier in fichiers:
                    try:
                        maj_couleur(client['nom'], "FTP", "yellow")
                        local_path = os.path.join(client['Rep_travail'], fichier)
                        with open(local_path, 'wb') as f:
                            ftp.retrbinary(f"RETR {fichier}", f.write)
                        nom_final = renommer_et_encoder(client, local_path)
                        if nom_final:
                            ftp.delete(fichier)
                            maj_couleur(client['nom'], "FTP", "green")
                        else:
                            maj_couleur(client['nom'], "FTP", "red")
                    except Exception as e:
                        logging.error(f"Erreur FTP {fichier} : {e}")
                        maj_couleur(client['nom'], "FTP", "red")

        elif client['protocol'] == 'FTPS':
            with ftplib.FTP_TLS(client['adresse'], client['user'], client['password']) as ftps:
                maj_couleur(client['nom'], "Connexion", "green")
                ftps.prot_p()
                ftps.cwd(client['dossier'])
                fichiers = ftps.nlst()
                for fichier in fichiers:
                    try:
                        maj_couleur(client['nom'], "FTP", "yellow")
                        local_path = os.path.join(client['Rep_travail'], fichier)
                        with open(local_path, 'wb') as f:
                            ftps.retrbinary(f"RETR {fichier}", f.write)
                        nom_final = renommer_et_encoder(client, local_path)
                        if nom_final:
                            ftps.delete(fichier)
                            maj_couleur(client['nom'], "FTP", "green")
                        else:
                            maj_couleur(client['nom'], "FTP", "red")
                    except Exception as e:
                        logging.error(f"Erreur FTPS {fichier} : {e}")
                        maj_couleur(client['nom'], "FTP", "red")

        else:
            logging.warning(f"Protocole inconnu pour {client['nom']}, tentative en local.")
            traiter_fichiers_localement(client, client['dossier'])

    except Exception as e:
        logging.error(f"Erreur lors du transfert pour {client['nom']} : {e}")
        maj_couleur(client['nom'], "Connexion", "red")
        maj_couleur(client['nom'], "FTP", "red")

# === RAFRAÎCHISSEMENT AUTOMATIQUE ===
def rafraichissement_automatique():
    while True:
        for client in clients:
            transferer_fichiers(client)
        time.sleep(10)

# === INTERFACE TKINTER ===
def creer_interface():
    root = tk.Tk()
    root.title("GETDA")
    root.geometry("550x250")
    root.attributes('-topmost', True)

    header = tk.Frame(root)
    header.pack(fill=tk.X)
    tk.Label(header, text="Nom", width=10).pack(side=tk.LEFT, padx=5)
    tk.Label(header, text="Connexion FTP", width=20).pack(side=tk.LEFT, padx=5)
    tk.Label(header, text="Fichier sur FTP", width=20).pack(side=tk.LEFT, padx=5)
    tk.Label(header, text="Fichier en traitement", width=20).pack(side=tk.LEFT, padx=5)

    for client in clients:
        row = tk.Frame(root)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=client['nom'], width=10, anchor="w").pack(side=tk.LEFT, padx=5)
        client_widgets[client['nom']] = {
            "Connexion": tk.Label(row, width=20, bg="green"),
            "FTP": tk.Label(row, width=20, bg="green"),
            "Reception": tk.Label(row, width=20, bg="green"),
        }
        client_widgets[client['nom']]["Connexion"].pack(side=tk.LEFT, padx=5)
        client_widgets[client['nom']]["FTP"].pack(side=tk.LEFT, padx=5)
        client_widgets[client['nom']]["Reception"].pack(side=tk.LEFT, padx=5)

    threading.Thread(target=rafraichissement_automatique, daemon=True).start()
    root.mainloop()

# === EXÉCUTION PRINCIPALE ===
if __name__ == "__main__":
    clients = charger_clients("param.xml")
    client_widgets = {}
    creer_interface()

