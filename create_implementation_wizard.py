# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectImplementationCreateWizard(models.TransientModel):
    _name = 'project.implementation.create.wizard'
    _description = 'Creează implementare (confirmare)'

    funding_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        required=True,
        domain="[('status_proiect', '=', 'contractat')]",
    )

    @api.constrains('funding_id')
    def _check_no_existing(self):
        for wiz in self:
            if not wiz.funding_id:
                continue
            if self.env['project.implementation'].search_count([('funding_project_id', '=', wiz.funding_id.id)]):
                raise ValidationError(_("Există deja o implementare pentru proiectul selectat."))

    def action_confirm_create(self):
        self.ensure_one()

        if self.funding_id.status_proiect != 'contractat':
            raise ValidationError(_("Implementarea poate fi creată doar pentru proiecte cu status „Contractat”."))

        impl = self.env['project.implementation'].create({
            'funding_project_id': self.funding_id.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Implementare proiect'),
            'res_model': 'project.implementation',
            'view_mode': 'form',
            'res_id': impl.id,
            'target': 'current',
        }