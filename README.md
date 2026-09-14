# Laptop bootstrap

Personal Linux recovery kit: unlock the encrypted cloud backup, clone GitHub projects, restore saved branches and local changes, then install the selected applications.

## On the new laptop

```bash
git clone https://github.com/uripg/laptop-bootstrap.git && cd laptop-bootstrap && bash bootstrap.sh
```

Run as your normal user in a terminal. Enter the recovery passphrase when asked. Installing packages may also ask for your Linux login password. Applications may need their own sign-in after installation.

The installer supports the Arch/Omarchy and Ubuntu/Pop!_OS/Debian package-manager families. Restore logic has passed a synthetic encrypted-backup round trip; a full installation on each Linux distribution has not yet been tested. Package availability may vary.

**First create the portable snapshot on the source Mac** by running `bootstrap-backup.command` from the private laptop-backup kit. Wait for `PORTABLE BACKUP COMPLETE`. The older full backup alone cannot supply this portable restore. The backup creation scripts and private project inventory are intentionally kept outside this public repository.

## What happens

1. Install missing recovery tools and request the recovery passphrase.
2. Download and verify the latest portable snapshot.
3. Clone private GitHub projects using the credential inside the encrypted snapshot.
4. Restore the saved commits and branches, unpublished Git history included in the snapshot, local edits, environment files, keys and selected settings.
5. Install the selected applications and development tools, with progress and a final report.

The portable payload has a 5 GB hard limit. Git clones and installed applications consume additional download and disk space. Documents, photos, local databases and large untracked data are separate from this portable setup. Keep the full backup until the new machine has been checked. Project-specific dependencies must still be installed when working in each project.

## Recovery and reruns

```bash
# Restore without installing applications
bash bootstrap.sh --skip-apps

# Select a specific portable snapshot
bash bootstrap.sh --snapshot SNAPSHOT_ID
```

Interrupted restores retain completed clones. Rerun with the same snapshot to resume. A newer repaired snapshot can also reuse clean clones from an incomplete restore when their repository and saved commit match. Edited or unrelated project folders are refused. Existing unrelated project folders are refused rather than overwritten. Replaced settings are preserved under `~/.local/state/uri-portable/`. Mac-specific shell settings and Keychain data are retained as references rather than activated on Linux. A completed snapshot is not reapplied over later edits.

## Public encrypted recovery file

`recovery.age` is password-encrypted ciphertext. It unlocks the cloud credentials and backup encryption password; the GitHub credential and project inventory are inside the encrypted cloud snapshot. No plaintext credentials or private project inventory belong in this repository.

Anyone can download this file and attempt password guesses offline. Use a strong, unique passphrase stored separately in a password manager. Deleting or replacing the public file cannot recall copies already downloaded. If the passphrase is compromised, rotate the underlying credentials and backup encryption access; changing the file alone does not revoke an old copy.

The cloud account, snapshot and GitHub access must remain available. The passphrase cannot be reset by this installer.
