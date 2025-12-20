# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


def _is_project_contracted(project):
    try:
        val = getattr(project, 'status_proiect', False)
        return bool(val and str(val).strip().lower() == 'contractat')
    except Exception:
        return False


class ProjectImplementation(models.Model):
    _name = 'project.implementation'
    _description = 'Implementare proiect'
    _rec_name = 'name'
    _order = 'id desc'

    funding_project_id = fields.Many2one('project.funding', string='Proiect finanțat', required=True, ondelete='restrict')
    name = fields.Char(string='Denumire proiect', related='funding_project_id.denumire', readonly=True)

    partner_id = fields.Many2one('res.partner', string='Beneficiar', compute='_compute_partner', store=False, readonly=True)
    user_id = fields.Many2one('res.users', string='Responsabil', default=lambda self: self.env.user)

    start_date = fields.Date(string='Data început')
    end_date = fields.Date(string='Data finalizare')
    description = fields.Text(string='Descriere')

    budget_line_ids = fields.Many2many('project.budget', string='Deviz (din proiect)',
                                       compute='_compute_budget_and_activity', store=False)
    activity_ids = fields.Many2many('project.activity', string='Activități (din proiect)',
                                    compute='_compute_budget_and_activity', store=False)
    purchase_ids = fields.Many2many('project.purchase', string='Achiziții (din proiect)',
                                    compute='_compute_purchase_ids', store=False)

    budget_line_count = fields.Integer(string='Nr. linii deviz', compute='_compute_counts')
    activity_count = fields.Integer(string='Nr. activități', compute='_compute_counts')
    purchase_count = fields.Integer(string='Nr. achiziții', compute='_compute_counts')

    contract_ids = fields.One2many('project.contract', 'implementation_id', string='Contracte')
    document_ids = fields.One2many('project.document', 'implementation_id', string='Documente')
    request_ids = fields.One2many('project.request', 'implementation_id', string='Solicitari')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    _sql_constraints = [
        ('unique_funding_project', 'unique(funding_project_id)', 'Pentru acest proiect există deja o implementare.'),
    ]

    @api.depends('funding_project_id')
    def _compute_partner(self):
        for rec in self:
            rec.partner_id = False
            if not rec.funding_project_id:
                continue
            for name in ('beneficiar', 'partner_id', 'partner'):
                if hasattr(rec.funding_project_id, name):
                    val = getattr(rec.funding_project_id, name)
                    try:
                        if hasattr(val, '_name') and val._name == 'res.partner':
                            rec.partner_id = val.id if val else False
                            break
                    except Exception:
                        pass
                    if isinstance(val, int):
                        partner = rec.env['res.partner'].browse(val)
                        if partner.exists():
                            rec.partner_id = partner.id
                            break

    @api.depends('funding_project_id')
    def _compute_budget_and_activity(self):
        for rec in self:
            if not rec.funding_project_id:
                rec.budget_line_ids = self.env['project.budget']
                rec.activity_ids = self.env['project.activity']
                continue
            rec.budget_line_ids = getattr(rec.funding_project_id, 'budget_line_ids', self.env['project.budget'])
            rec.activity_ids = getattr(rec.funding_project_id, 'activity_ids', self.env['project.activity'])

    @api.depends('funding_project_id')
    def _compute_purchase_ids(self):
        for rec in self:
            if not rec.funding_project_id:
                rec.purchase_ids = self.env['project.purchase']
            else:
                rec.purchase_ids = self.env['project.purchase'].search([('project_id', '=', rec.funding_project_id.id)])

    @api.depends('budget_line_ids', 'activity_ids', 'purchase_ids')
    def _compute_counts(self):
        for rec in self:
            rec.budget_line_count = len(rec.budget_line_ids or [])
            rec.activity_count = len(rec.activity_ids or [])
            rec.purchase_count = len(rec.purchase_ids or [])

    @api.model_create_multi
    def create(self, vals_list):
        to_create = []
        for vals in vals_list:
            if not isinstance(vals, dict):
                raise ValidationError('Invalid data for creation (expected dict).')
            project_id = vals.get('funding_project_id')
            if not project_id:
                raise ValidationError('Trebuie specificat proiectul finanțat.')
            project = self.env['project.funding'].browse(project_id)
            if not project.exists():
                raise ValidationError('Proiectul specificat nu există.')
            if not _is_project_contracted(project):
                raise ValidationError('Implementarea poate fi creată doar pentru proiecte cu status "Contractat".')
            if not vals.get('start_date'):
                vals['start_date'] = getattr(project, 'data_semnare', getattr(project, 'data_depunere', getattr(project, 'start_date', False)))
            if not vals.get('end_date'):
                vals['end_date'] = getattr(project, 'data_finalizare', getattr(project, 'end_date', False))
            to_create.append(vals)
        return super(ProjectImplementation, self).create(to_create)

    @api.constrains('funding_project_id')
    def _check_funding_project_status(self):
        for rec in self:
            if not rec.funding_project_id:
                continue
            if not _is_project_contracted(rec.funding_project_id):
                raise ValidationError('Implementarea poate fi asociată doar cu proiecte în stadiul "Contractat".')

    def _action_for_model_with_ids(self, model_name, ids, name, view_mode='tree,form'):
        ids = list(map(int, ids)) if ids else []
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model_name,
            'view_mode': view_mode,
            'domain': [('id', 'in', ids)],
            'context': {},
            'target': 'current',
        }

    def action_open_budget(self):
        self.ensure_one()
        ids = self.budget_line_ids.ids if self.budget_line_ids else []
        return self._action_for_model_with_ids('project.budget', ids, _('Buget'))

    def action_open_activities(self):
        self.ensure_one()
        ids = self.activity_ids.ids if self.activity_ids else []
        return self._action_for_model_with_ids('project.activity', ids, _('Activități'))

    def action_open_purchases(self):
        self.ensure_one()
        ids = self.purchase_ids.ids if self.purchase_ids else []
        return self._action_for_model_with_ids('project.purchase', ids, _('Achiziții'))

    def action_open_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracte'),
            'res_model': 'project.contract',
            'view_mode': 'tree,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {'default_implementation_id': self.id},
            'target': 'current',
        }

    def action_open_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documente'),
            'res_model': 'project.document',
            'view_mode': 'tree,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {'default_implementation_id': self.id},
            'target': 'current',
        }

    def action_open_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitări'),
            'res_model': 'project.request',
            'view_mode': 'tree,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {'default_implementation_id': self.id},
            'target': 'current',
        }


class ProjectContract(models.Model):
    _name = 'project.contract'
    _description = 'Contract proiect (placeholder)'

    name = fields.Char(string='Denumire contract', required=True)
    implementation_id = fields.Many2one('project.implementation', string='Implementare', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partener')
    date_signed = fields.Date(string='Data semnării')
    file_id = fields.Many2one('ir.attachment', string='Document semnat')
    state = fields.Selection([('draft', 'Draft'), ('signed', 'Signed'), ('cancel', 'Cancelled')], default='draft')


class ProjectDocument(models.Model):
    _name = 'project.document'
    _description = 'Document proiect (placeholder)'

    name = fields.Char(string='Denumire document', required=True)
    implementation_id = fields.Many2one('project.implementation', string='Implementare', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partener')
    date = fields.Date(string='Data document')
    line_ids = fields.One2many('project.document.line', 'document_id', string='Linii document')


class ProjectDocumentLine(models.Model):
    _name = 'project.document.line'
    _description = 'Linii document (placeholder)'

    document_id = fields.Many2one('project.document', string='Document', ondelete='cascade')
    budget_line_id = fields.Many2one('project.budget', string='Linie deviz (legată)')
    description = fields.Char(string='Descriere')
    amount = fields.Monetary(string='Valoare', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Monedă', default=lambda self: self.env.company.currency_id)

    @api.onchange('document_id')
    def _onchange_document(self):
        if self.document_id and self.document_id.implementation_id \
                and getattr(self.document_id.implementation_id, 'funding_project_id', False):
            allowed = self.document_id.implementation_id.funding_project_id.budget_line_ids.ids or []
            return {'domain': {'budget_line_id': [('id', 'in', allowed)]}}
        return {'domain': {'budget_line_id': []}}


class ProjectRequest(models.Model):
    _name = 'project.request'
    _description = 'Solicitare proiect (placeholder)'

    name = fields.Char(string='Referință', required=True)
    implementation_id = fields.Many2one('project.implementation', string='Implementare', ondelete='cascade')
    document_line_id = fields.Many2one('project.document.line', string='Linie document')
    amount = fields.Monetary(string='Valoare', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Monedă', default=lambda self: self.env.company.currency_id)
    description = fields.Text(string='Descriere')
    state = fields.Selection([('draft', 'Draft'), ('sent', 'Sent'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='draft')


class ProjectPurchase(models.Model):
    _name = 'project.purchase'
    _description = 'Achiziții proiect (placeholder)'

    project_id = fields.Many2one('project.funding', string='Proiect', ondelete='cascade')
    name = fields.Char(string='Referință achiziție', required=True)
    furnizor = fields.Char(string='Furnizor')
    partner_id = fields.Many2one('res.partner', string='Partener')
    data = fields.Date(string='Data')
    date_order = fields.Date(string='Data comandă')
    valoare = fields.Float(string='Valoare')
    amount_total = fields.Monetary(string='Valoare totală', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Monedă', default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('draft', 'Draft'), ('sent', 'Sent'),
        ('confirmed', 'Confirmed'), ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], default='draft')