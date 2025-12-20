# -*- coding: utf-8 -*-
{
    "name": "Project Implementation UI",
    "version": "1.0.2",
    "summary": "UI helpers for creating/opening project implementations",
    "description": "Adds a Manage Implementation button and a list of funded projects with status 'contractat'.",
    "author": "officeedumax-dot",
    "license": "AGPL-3",
    "category": "Project",
    "depends": ["base", "project_funding"],
    "data": [
        "security/ir.model.access.csv",
        "views/project_funding_views.xml",
        "views/implementation_views.xml",
        "views/implementation_wizard_views.xml",
        "views/implementation_actions_menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}