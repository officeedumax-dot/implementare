# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectImplementation(models.Model):
    _name = 'project.implementation'
    _description = 'Implementare proiect'
    _order = 'id desc'
    _rec_name = 'name'

    funding_project_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        required=True,
        ondelete='restrict',
        index=True,
    )

    beneficiar_name = fields.Char(
        string='Beneficiar',
        related='funding_project_id.beneficiar',
        store=False,
        readonly=True,
    )

    beneficiar_cui = fields.Char(
        string='CUI',
        related='funding_project_id.cui',
        store=False,
        readonly=True,
    )


    name = fields.Char(
        string='Denumire proiect',
        related='funding_project_id.denumire',
        store=False,
        readonly=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='Responsabil implementare',
        default=lambda self: self.env.user,
    )

    start_date = fields.Date(string='Data început')
    end_date = fields.Date(string='Data finalizare')
    description = fields.Text(string='Descriere implementare')

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('in_progress', 'În implementare'),
            ('done', 'Finalizat'),
            ('cancel', 'Anulat'),
        ],
        string='Status',
        default='draft',
    )

    # -------------------------
    # Implementation-owned data
    # -------------------------
    contract_ids = fields.One2many('project.contract', 'implementation_id', string='Contracte')
    document_ids = fields.One2many('project.document', 'implementation_id', string='Documente')
    request_ids = fields.One2many('project.request', 'implementation_id', string='Solicitări de plată')
    settlement_ids = fields.One2many('project.settlement', 'implementation_id', string='Decontări')

    # -------------------------
    # Deviz proxy (mirror + calc fields)
    # -------------------------
    budget_proxy_line_ids = fields.One2many(
        'project.implementation.budget.line',
        'implementation_id',
        string='Deviz (proxy)',
    )

    # -------------------------
    # Achiziții proxy (mirror + calc fields)
    # -------------------------
    acquisition_proxy_line_ids = fields.One2many(
        'project.implementation.acquisition.line',
        'implementation_id',
        string='Achiziții (proxy)',
    )

    # -------------------------
    # Activități proxy (mirror + calc fields)
    # -------------------------
    activity_proxy_line_ids = fields.One2many(
        'project.implementation.activity.line',
        'implementation_id',
        string='Activități (proxy)',
    )

    _sql_constraints = [
        (
            'unique_funding_project',
            'unique(funding_project_id)',
            'Există deja o implementare pentru acest proiect finanțat.',
        )
    ]

    # =========================
    # VALIDĂRI
    # =========================
    @api.constrains('funding_project_id')
    def _check_project_status(self):
        for rec in self:
            if rec.funding_project_id and rec.funding_project_id.status_proiect != 'contractat':
                raise ValidationError(
                    _('Implementarea poate fi creată doar pentru proiecte cu status „Contractat”.')
                )

    def write(self, vals):
        # nu permitem schimbarea proiectului finanțat după creare
        if 'funding_project_id' in vals:
            raise ValidationError(_("Nu puteți schimba proiectul finanțat pe o implementare existentă."))
        return super().write(vals)

    @api.model
    def action_open_create_implementation_wizard(self):
        """Deschide wizard-ul de creare implementare și exclude proiectele care au deja implementare."""
        excluded_ids = self.search([]).mapped('funding_project_id').ids
        action = self.env.ref('project_implementation.action_project_implementation_create_wizard').read()[0]
        action['context'] = dict(self.env.context, excluded_funding_ids=excluded_ids)
        return action

    # =========================
    # DEVIZ SYNC (FUNDING -> PROXY) + REFRESH FORM
    # =========================
    def action_sync_budget_from_funding(self):
        """Generează liniile proxy pe baza devizului din funding (read-only source) și face refresh la form."""
        self.ensure_one()

        funding_lines = self.funding_project_id.budget_line_ids
        existing_funding_line_ids = {l.funding_budget_line_id.id for l in self.budget_proxy_line_ids}

        to_create = [
            {'implementation_id': self.id, 'funding_budget_line_id': fline.id}
            for fline in funding_lines
            if fline.id not in existing_funding_line_ids
        ]

        if to_create:
            self.env['project.implementation.budget.line'].create(to_create)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Implementare proiect'),
            'res_model': 'project.implementation',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': dict(self.env.context),
        }

    # =========================
    # ACHIZIȚII SYNC (FUNDING -> PROXY) + REFRESH FORM
    # =========================
    def action_sync_acquisitions_from_funding(self):
        """Generează liniile proxy pe baza achizițiilor din funding (read-only source) și face refresh la form."""
        self.ensure_one()

        funding_acquisitions = self.env['project.acquisition'].search([
            ('project_id', '=', self.funding_project_id.id),
        ], order='sequence, id')

        existing_funding_acq_ids = {l.funding_acquisition_id.id for l in self.acquisition_proxy_line_ids}

        to_create = [
            {'implementation_id': self.id, 'funding_acquisition_id': acq.id}
            for acq in funding_acquisitions
            if acq.id not in existing_funding_acq_ids
        ]

        if to_create:
            self.env['project.implementation.acquisition.line'].create(to_create)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Implementare proiect'),
            'res_model': 'project.implementation',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': dict(self.env.context),
        }

    # =========================
    # ACTIVITĂȚI SYNC (FUNDING -> PROXY) + REFRESH FORM
    # =========================
    def action_sync_activities_from_funding(self):
        """Generează liniile proxy pe baza activităților din funding (read-only source) și face refresh la form."""
        self.ensure_one()

        funding_activities = self.env['project.activity'].search([
            ('project_id', '=', self.funding_project_id.id),
        ], order='sequence, id')

        existing_funding_act_ids = {l.funding_activity_id.id for l in self.activity_proxy_line_ids}

        to_create = [
            {'implementation_id': self.id, 'funding_activity_id': act.id}
            for act in funding_activities
            if act.id not in existing_funding_act_ids
        ]

        if to_create:
            self.env['project.implementation.activity.line'].create(to_create)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Implementare proiect'),
            'res_model': 'project.implementation',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': dict(self.env.context),
        }

    # =========================
    # ACTIONS (read-only pentru funding)
    # =========================
    def action_open_activities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Activități proiect'),
            'res_model': 'project.activity',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.funding_project_id.id)],
            'context': {'create': False, 'delete': False},
            'target': 'current',
        }

    def action_open_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Achiziții proiect'),
            'res_model': 'project.acquisition',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.funding_project_id.id)],
            'context': {'create': False, 'delete': False},
            'target': 'current',
        }

    def action_open_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracte'),
            'res_model': 'project.contract',
            'view_mode': 'list,form',
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
            'view_mode': 'list,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {'default_implementation_id': self.id},
            'target': 'current',
        }

    def action_open_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitări de plată'),
            'res_model': 'project.request',
            'view_mode': 'list,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {'default_implementation_id': self.id},
            'target': 'current',
        }

    file_ids = fields.One2many('project.file', 'implementation_id', string='Fișiere')

    def action_open_files_manager(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fișiere proiect'),
            'res_model': 'project.file',
            'view_mode': 'list,form',
            'domain': [('implementation_id', '=', self.id)],
            'context': {
                'default_implementation_id': self.id,
                'default_funding_project_id': self.funding_project_id.id,
                'default_res_model': 'project.implementation',
                'default_res_id': self.id,
            },
            'target': 'current',
        }

class ProjectImplementationAcquisitionLine(models.Model):
    _name = 'project.implementation.acquisition.line'
    _description = 'Linie achiziție (proxy implementare)'
    _order = 'sequence, id'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='cascade',
        index=True,
    )

    funding_project_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        related='implementation_id.funding_project_id',
        store=False,
        readonly=True,
    )

    funding_acquisition_id = fields.Many2one(
        'project.acquisition',
        string='Achiziție (funding)',
        required=True,
        ondelete='restrict',
        domain="[('project_id', '=', funding_project_id)]",
        index=True,
    )

    # Mirror fields (read-only) - UPDATED per cerință
    name = fields.Char(string='Denumire achiziție', related='funding_acquisition_id.name', store=False, readonly=True)
    code = fields.Char(string='Cod achiziție', related='funding_acquisition_id.code', store=False, readonly=True)
    sequence = fields.Integer(string='Ordine', related='funding_acquisition_id.sequence', store=False, readonly=True)

    date_start = fields.Date(string='Data început', related='funding_acquisition_id.date_start', store=False, readonly=True)
    date_end = fields.Date(string='Data sfârșit', related='funding_acquisition_id.date_end', store=False, readonly=True)

    deviz_baza = fields.Float(string='Bază (deviz)', related='funding_acquisition_id.baza', store=False, readonly=True)
    deviz_tva = fields.Float(string='TVA (deviz)', related='funding_acquisition_id.tva', store=False, readonly=True)

    # Contracted totals (from contracts in this implementation linked to this acquisition)
    amount_contracted_base = fields.Monetary(
        string='Contractat bază',
        currency_field='currency_id',
        compute='_compute_contracted_amounts',
        store=False,
        readonly=True,
    )
    amount_contracted_vat = fields.Monetary(
        string='Contractat TVA',
        currency_field='currency_id',
        compute='_compute_contracted_amounts',
        store=False,
        readonly=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Monedă',
        default=lambda self: self.env.company.currency_id,
        required=True,
        readonly=True,
    )

    @api.depends(
        'implementation_id.contract_ids',
        'implementation_id.contract_ids.acquisition_id',
        'implementation_id.contract_ids.line_ids',
        'implementation_id.contract_ids.line_ids.base_amount',
        'implementation_id.contract_ids.line_ids.vat_amount',
    )
    def _compute_contracted_amounts(self):
        for rec in self:
            contracts = rec.implementation_id.contract_ids.filtered(
                lambda c: c.acquisition_id and c.acquisition_id.id == rec.funding_acquisition_id.id
            )
            lines = contracts.mapped('line_ids')
            rec.amount_contracted_base = sum(lines.mapped('base_amount') or [0.0])
            rec.amount_contracted_vat = sum(lines.mapped('vat_amount') or [0.0])


class ProjectImplementationActivityLine(models.Model):
    _name = 'project.implementation.activity.line'
    _description = 'Linie activitate (proxy implementare)'
    _order = 'sequence, id'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='cascade',
        index=True,
    )

    funding_project_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        related='implementation_id.funding_project_id',
        store=False,
        readonly=True,
    )

    funding_activity_id = fields.Many2one(
        'project.activity',
        string='Activitate (funding)',
        required=True,
        ondelete='restrict',
        domain="[('project_id', '=', funding_project_id)]",
        index=True,
    )

    # Mirror fields (read-only) - kept generic to avoid depending on exact activity model fields
    name = fields.Char(string='Denumire', related='funding_activity_id.name', store=False, readonly=True)
    sequence = fields.Integer(string='Ordine', related='funding_activity_id.sequence', store=False, readonly=True)
    date_start = fields.Date(string='Data început (plan)', related='funding_activity_id.date_start', store=False, readonly=True)
    date_end = fields.Date(string='Data sfârșit (plan)', related='funding_activity_id.date_end', store=False, readonly=True)

    min_contract_date = fields.Date(
        string='Min contract',
        compute='_compute_contract_date_bounds',
        store=False,
        readonly=True,
    )
    max_contract_date = fields.Date(
        string='Max contract',
        compute='_compute_contract_date_bounds',
        store=False,
        readonly=True,
    )

    @api.depends(
        'implementation_id.contract_ids',
        'implementation_id.contract_ids.activity_id',
        'implementation_id.contract_ids.start_date',
        'implementation_id.contract_ids.end_date',
    )
    def _compute_contract_date_bounds(self):
        for rec in self:
            contracts = rec.implementation_id.contract_ids.filtered(
                lambda c: c.activity_id and c.activity_id.id == rec.funding_activity_id.id
            )

            starts = [d for d in contracts.mapped('start_date') if d]
            ends = [d for d in contracts.mapped('end_date') if d]

            rec.min_contract_date = min(starts) if starts else False
            rec.max_contract_date = max(ends) if ends else False


# =====================================================
# Baseline models (kept here for now)
# =====================================================

class ProjectRequest(models.Model):
    _name = 'project.request'
    _description = 'Solicitare de plată'

    name = fields.Char(string='Referință', required=True)
    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        ondelete='cascade',
        required=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    amount = fields.Monetary(string='Valoare', currency_field='currency_id')

    state = fields.Selection(
        [('draft', 'Draft'), ('sent', 'Trimis'), ('approved', 'Aprobat')],
        default='draft',
    )