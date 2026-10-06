"""Bygger om hemsidan och lägger upp allas fynd från befintlig data – utan att leta nya fynd.
Används av snabbpubliceringen när bara sidans utseende ändrats."""
import main
import sajt
import smak
from databas import Databas

cfg = main.las_config()
export = smak.hamta(cfg)
smak.tillampa(cfg, export)
db = Databas()
sajt.bygg(db, cfg)
smak.publicera(cfg, sajt.anvandarfynd(db, cfg))
