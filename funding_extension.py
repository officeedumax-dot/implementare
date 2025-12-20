# -*- coding: utf-8 -*-
from odoo import models, fields, _


class ProjectFunding(models.Model):
    _inherit = 'project.funding'

    # Beneficiar ca partener (Many2one) – folosit de implementare pentru a popula partner_id
    partner_id = fields.Many2one('res.partner', string='Beneficiar (partener)')

    def action_manage_implementation(self):
        """If implementation exists -> open it. Otherwise open wizard to ask creation."""
        self.ensure_one()
        impl = self.env['project.implementation'].search([('funding_project_id', '=', self.id)], limit=1)
        if impl:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Implementation'),
                'res_model': 'project.implementation',
                'view_mode': 'form',
                'res_id': impl.id,
                'target': 'current',
            }
        # open wizard modal, pass funding id in context
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Implementation'),
            'res_model': 'project.implementation.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_funding_id': self.id},
        }

    # Optional: sincronizează textul beneficiar cu partenerul ales
    def _update_beneficiar_from_partner(self):
        for rec in self:
            if rec.partner_id and not getattr(rec, 'beneficiar', False):
                rec.beneficiar = rec.partner_id.name

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._update_beneficiar_from_partner()
        return res

    def create(self, vals_list):
        records = super().create(vals_list)
        records._update_beneficiar_from_partner()
        return records