# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectImplementationCreateWizard(models.TransientModel):
    _name = 'project.implementation.create.wizard'
    _description = 'Wizard to create implementation structure for a funding project'

    funding_id = fields.Many2one('project.funding', string='Proiect finanțat', required=True)
    message = fields.Text(string='Mesaj', readonly=True,
                          default="Doriți să creați structura de implementare pentru acest proiect?")

    def action_create_implementation(self):
        """Create the project.implementation record and open it."""
        self.ensure_one()
        funding = self.funding_id
        if not funding:
            raise UserError(_('Nu este selectat niciun proiect.'))

        # check again if implementation exists (race-safe)
        impl = self.env['project.implementation'].search([('funding_project_id', '=', funding.id)], limit=1)
        if impl:
            # already exists, open it
            return {
                'type': 'ir.actions.act_window',
                'name': _('Implementation'),
                'res_model': 'project.implementation',
                'view_mode': 'form',
                'res_id': impl.id,
                'target': 'current',
            }

        # prepare vals: copy sensible dates from funding
        vals = {
            'funding_project_id': funding.id,
        }
        # attempt to find appropriate date fields on funding (common names)
        start = getattr(funding, 'data_semnare', False) or getattr(funding, 'data_depunere', False) or getattr(funding, 'start_date', False) or getattr(funding, 'date_start', False)
        end = getattr(funding, 'data_finalizare', False) or getattr(funding, 'end_date', False) or getattr(funding, 'date_end', False)

        if start:
            vals['start_date'] = start
        if end:
            vals['end_date'] = end

        impl_rec = self.env['project.implementation'].create(vals)

        # Optionally: create additional structure (tasks/lines) here if needed.

        return {
            'type': 'ir.actions.act_window',
            'name': _('Implementation created'),
            'res_model': 'project.implementation',
            'view_mode': 'form',
            'res_id': impl_rec.id,
            'target': 'current',
        }

    def action_cancel(self):
        """Close wizard without action."""
        return {'type': 'ir.actions.act_window_close'}