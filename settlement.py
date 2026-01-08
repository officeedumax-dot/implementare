# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectSettlement(models.Model):
    _name = 'project.settlement'
    _description = 'Decontare proiect'
    _order = 'settlement_date desc, id desc'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='restrict',
        index=True,
    )

    funding_project_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        related='implementation_id.funding_project_id',
        store=False,
        readonly=True,
    )

    aport_valoare = fields.Float(
        string='Valoare aport (lei)',
        related='funding_project_id.aport_valoare',
        store=False,
        readonly=True,
    )

    settlement_number = fields.Char(string='Număr decontare', required=True, index=True)
    settlement_date = fields.Date(string='Data decontare', required=True)
    notes = fields.Text(string='Observații')

    line_ids = fields.One2many('project.settlement.line', 'settlement_id', string='Linii decontare')

    amount_elig_base_total = fields.Float(string='Total bază eligibil decontat', compute='_compute_totals', store=False)
    amount_elig_vat_total = fields.Float(string='Total TVA eligibil decontat', compute='_compute_totals', store=False)
    amount_total = fields.Float(string='Total decontare', compute='_compute_totals', store=False)

    @api.depends('line_ids.elig_base_amount', 'line_ids.elig_vat_amount')
    def _compute_totals(self):
        for rec in self:
            base = sum(rec.line_ids.mapped('elig_base_amount') or [0.0])
            vat = sum(rec.line_ids.mapped('elig_vat_amount') or [0.0])
            rec.amount_elig_base_total = base
            rec.amount_elig_vat_total = vat
            rec.amount_total = (base or 0.0) + (vat or 0.0)

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalii decontare'),
            'res_model': 'project.settlement',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_settlement_form_details').id, 'form')],
            'res_id': self.id,
            'target': 'new',
            'context': dict(self.env.context),
        }

    # ----------------------------
    # NEW: blocăm ștergerea decontării dacă are linii
    # ----------------------------
    def unlink(self):
        for rec in self:
            if rec.line_ids:
                raise ValidationError(_(
                    "Nu puteți șterge decontarea deoarece are linii de decontare.\n\n"
                    "Decontare: %(sett)s\n"
                    "Număr linii: %(cnt)s\n\n"
                    "Ștergeți mai întâi liniile din „Detalii decontare”, apoi ștergeți decontarea."
                ) % {
                    'sett': rec.display_name,
                    'cnt': len(rec.line_ids),
                })
        return super().unlink()


class ProjectSettlementLine(models.Model):
    _name = 'project.settlement.line'
    _description = 'Linie decontare'
    _order = 'id'

    settlement_id = fields.Many2one(
        'project.settlement',
        string='Decontare',
        required=True,
        ondelete='cascade',
        index=True,
    )

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        related='settlement_id.implementation_id',
        store=False,
        readonly=True,
    )

    document_line_id = fields.Many2one(
        'project.document.line',
        string='Linie document',
        required=True,
        ondelete='restrict',
        domain="[('document_id.implementation_id', '=', implementation_id)]",
        index=True,
    )

    # info pentru identificare
    document_id = fields.Many2one('project.document', related='document_line_id.document_id', store=False, readonly=True)
    document_number = fields.Char(related='document_id.document_number', store=False, readonly=True)
    document_date = fields.Date(related='document_id.document_date', store=False, readonly=True)
    issuer_name = fields.Char(related='document_id.issuer_name', store=False, readonly=True)

    # sume decontate (eligibil) - introduse pe linia de decont
    elig_base_amount = fields.Float(string='Bază eligibil decontat', default=0.0)
    elig_vat_amount = fields.Float(string='TVA eligibil decontat', default=0.0)

    # ----------------------------
    # TVA eligibil decontat (auto 21% cu override manual)
    # ----------------------------
    vat_rate = fields.Float(string='Cota TVA (%)', default=21.0)
    elig_vat_manual = fields.Boolean(string='TVA eligibil manual', default=False)

    @api.onchange('elig_base_amount', 'vat_rate')
    def _onchange_settlement_elig_vat_auto(self):
        for rec in self:
            if rec.elig_vat_manual:
                continue
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.elig_vat_amount = (rec.elig_base_amount or 0.0) * rate

    @api.onchange('elig_vat_amount')
    def _onchange_settlement_elig_vat_manual_flag(self):
        for rec in self:
            rec.elig_vat_manual = True

    def action_reset_settlement_vat_auto(self):
        for rec in self:
            rec.elig_vat_manual = False
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.elig_vat_amount = (rec.elig_base_amount or 0.0) * rate

    # ----------------------------
    # Coef nerambursabil = 1 - aport_coef
    # ----------------------------
    neramb_coef = fields.Float(string='Coef nerambursabil', compute='_compute_neramb_coef', store=False)

    @api.depends('implementation_id.funding_project_id.aport_coef')
    def _compute_neramb_coef(self):
        for rec in self:
            funding = rec.implementation_id.funding_project_id
            aport_coef = getattr(funding, 'aport_coef', 0.0) or 0.0
            rec.neramb_coef = max(0.0, 1.0 - aport_coef)

    # ----------------------------
    # Linie Deviz (prin document_line -> contract_line -> budget_proxy_line)
    # ----------------------------
    budget_proxy_line_id = fields.Many2one(
        'project.implementation.budget.line',
        string='Linie deviz (din document)',
        related='document_line_id.budget_proxy_line_id',
        store=False,
        readonly=True,
    )

    # Rând 1 (Plan)
    budget_elig_base = fields.Float(string='Deviz: eligibil bază', compute='_compute_budget_panel', store=False)
    budget_elig_vat = fields.Float(string='Deviz: eligibil TVA', compute='_compute_budget_panel', store=False)
    budget_neramb_base = fields.Float(string='Deviz: neramb bază', compute='_compute_budget_panel', store=False)
    budget_neramb_vat = fields.Float(string='Deviz: neramb TVA', compute='_compute_budget_panel', store=False)

    # Rând 2 (Decontat - DB, exclude linia curentă)
    budget_settled_base = fields.Float(string='Deviz: bază decontat', compute='_compute_budget_panel', store=False)
    budget_settled_vat = fields.Float(string='Deviz: TVA decontat', compute='_compute_budget_panel', store=False)
    budget_settled_total = fields.Float(string='Deviz: total decontat', compute='_compute_budget_panel', store=False)

    # Rând 3 (Diferență)
    budget_diff_base = fields.Float(string='Deviz: diferență bază', compute='_compute_budget_panel', store=False)
    budget_diff_vat = fields.Float(string='Deviz: diferență TVA', compute='_compute_budget_panel', store=False)
    budget_diff_total = fields.Float(string='Deviz: diferență total', compute='_compute_budget_panel', store=False)

    @api.depends(
        'budget_proxy_line_id',
        'neramb_coef',
        'implementation_id',
        'document_line_id',
        'elig_base_amount',
        'elig_vat_amount',
        'implementation_id.settlement_ids.line_ids.elig_base_amount',
        'implementation_id.settlement_ids.line_ids.elig_vat_amount',
        'implementation_id.settlement_ids.line_ids.document_line_id',
    )
    def _compute_budget_panel(self):
        # ---- 1) PLAN ----
        for rec in self:
            b = rec.budget_proxy_line_id
            if b and b.funding_budget_line_id:
                fline = b.funding_budget_line_id
                rec.budget_elig_base = fline.chelt_elig_baza or 0.0
                rec.budget_elig_vat = fline.chelt_elig_tva or 0.0
            else:
                rec.budget_elig_base = 0.0
                rec.budget_elig_vat = 0.0

            coef = rec.neramb_coef or 0.0
            rec.budget_neramb_base = (rec.budget_elig_base or 0.0) * coef
            rec.budget_neramb_vat = (rec.budget_elig_vat or 0.0) * coef

        # ---- 2) DECONTAT (batch: 1 search per implementation, agregare python) ----
        by_impl = {}
        for rec in self:
            if rec.implementation_id and rec.budget_proxy_line_id:
                by_impl.setdefault(rec.implementation_id.id, set()).add(rec.budget_proxy_line_id.id)

        totals = {}  # (impl_id, budget_proxy_id) -> (sum_base, sum_vat)

        if by_impl:
            for impl_id, budget_ids in by_impl.items():
                lines = self.env['project.settlement.line'].search([
                    ('settlement_id.implementation_id', '=', impl_id),
                    ('document_line_id.budget_proxy_line_id', 'in', list(budget_ids)),
                ])
                for l in lines:
                    bpl = l.document_line_id.budget_proxy_line_id
                    if not bpl:
                        continue
                    key = (impl_id, bpl.id)
                    base, vat = totals.get(key, (0.0, 0.0))
                    totals[key] = (base + (l.elig_base_amount or 0.0), vat + (l.elig_vat_amount or 0.0))

        # ---- 3) Setăm valori, excluzând linia curentă (prin scădere) ----
        for rec in self:
            if rec.implementation_id and rec.budget_proxy_line_id:
                key = (rec.implementation_id.id, rec.budget_proxy_line_id.id)
                total_base, total_vat = totals.get(key, (0.0, 0.0))

                if rec.id:
                    total_base -= (rec.elig_base_amount or 0.0)
                    total_vat -= (rec.elig_vat_amount or 0.0)

                rec.budget_settled_base = total_base
                rec.budget_settled_vat = total_vat
            else:
                rec.budget_settled_base = 0.0
                rec.budget_settled_vat = 0.0

            rec.budget_settled_total = (rec.budget_settled_base or 0.0) + (rec.budget_settled_vat or 0.0)
            rec.budget_diff_base = (rec.budget_neramb_base or 0.0) - (rec.budget_settled_base or 0.0)
            rec.budget_diff_vat = (rec.budget_neramb_vat or 0.0) - (rec.budget_settled_vat or 0.0)
            rec.budget_diff_total = (rec.budget_diff_base or 0.0) + (rec.budget_diff_vat or 0.0)

    # ----------------------------
    # Linie Document (plan + decontat + diferență)
    # ----------------------------
    doc_elig_base = fields.Float(string='Doc: eligibil bază', compute='_compute_document_panel', store=False)
    doc_elig_vat = fields.Float(string='Doc: eligibil TVA', compute='_compute_document_panel', store=False)
    doc_neramb_base = fields.Float(string='Doc: neramb bază', compute='_compute_document_panel', store=False)
    doc_neramb_vat = fields.Float(string='Doc: neramb TVA', compute='_compute_document_panel', store=False)

    # Decontat - DB, exclude linia curentă (LOGICĂ IDENTICĂ CU DEVIZ)
    doc_settled_base = fields.Float(string='Doc: bază decontat', compute='_compute_document_panel', store=False)
    doc_settled_vat = fields.Float(string='Doc: TVA decontat', compute='_compute_document_panel', store=False)

    # Diferență
    doc_diff_base = fields.Float(string='Doc: diferență bază', compute='_compute_document_panel', store=False)
    doc_diff_vat = fields.Float(string='Doc: diferență TVA', compute='_compute_document_panel', store=False)

    @api.depends(
        'document_line_id',
        'neramb_coef',
        'implementation_id',
        'elig_base_amount',
        'elig_vat_amount',
        'implementation_id.settlement_ids.line_ids.elig_base_amount',
        'implementation_id.settlement_ids.line_ids.elig_vat_amount',
        'implementation_id.settlement_ids.line_ids.document_line_id',
    )
    def _compute_document_panel(self):
        # ---- 1) PLAN ----
        for rec in self:
            dl = rec.document_line_id
            rec.doc_elig_base = (dl.elig_base_amount or 0.0) if dl else 0.0
            rec.doc_elig_vat = (dl.elig_vat_amount or 0.0) if dl else 0.0

            coef = rec.neramb_coef or 0.0
            rec.doc_neramb_base = (rec.doc_elig_base or 0.0) * coef
            rec.doc_neramb_vat = (rec.doc_elig_vat or 0.0) * coef

        # ---- 2) DECONTAT (batch: 1 search per implementation, agregare python) ----
        by_impl = {}
        for rec in self:
            if rec.implementation_id and rec.document_line_id:
                by_impl.setdefault(rec.implementation_id.id, set()).add(rec.document_line_id.id)

        totals = {}  # (impl_id, document_line_id) -> (sum_base, sum_vat)

        if by_impl:
            for impl_id, doc_line_ids in by_impl.items():
                lines = self.env['project.settlement.line'].search([
                    ('settlement_id.implementation_id', '=', impl_id),
                    ('document_line_id', 'in', list(doc_line_ids)),
                ])
                for l in lines:
                    if not l.document_line_id:
                        continue
                    key = (impl_id, l.document_line_id.id)
                    base, vat = totals.get(key, (0.0, 0.0))
                    totals[key] = (base + (l.elig_base_amount or 0.0), vat + (l.elig_vat_amount or 0.0))

        # ---- 3) Setăm valori, excluzând linia curentă (prin scădere) ----
        for rec in self:
            if rec.implementation_id and rec.document_line_id:
                key = (rec.implementation_id.id, rec.document_line_id.id)
                total_base, total_vat = totals.get(key, (0.0, 0.0))

                if rec.id:
                    total_base -= (rec.elig_base_amount or 0.0)
                    total_vat -= (rec.elig_vat_amount or 0.0)

                rec.doc_settled_base = total_base
                rec.doc_settled_vat = total_vat
            else:
                rec.doc_settled_base = 0.0
                rec.doc_settled_vat = 0.0

            rec.doc_diff_base = (rec.doc_neramb_base or 0.0) - (rec.doc_settled_base or 0.0)
            rec.doc_diff_vat = (rec.doc_neramb_vat or 0.0) - (rec.doc_settled_vat or 0.0)

    # ----------------------------
    # Autofill: la selectare linie document => completează cu diferențele rămase pe document
    # (Doc: diferență bază / Doc: diferență TVA), pentru a ușura utilizatorul.
    # ----------------------------
    @api.onchange('document_line_id')
    def _onchange_document_line_id_autofill(self):
        for rec in self:
            if not rec.document_line_id or not rec.implementation_id:
                rec.elig_base_amount = 0.0
                rec.elig_vat_amount = 0.0
                rec.elig_vat_manual = False
                continue

            # forțăm recalc ca să avem doc_diff_* corecte în cache-ul curent
            rec._compute_document_panel()

            remaining_base = max(0.0, rec.doc_diff_base or 0.0)
            remaining_vat = max(0.0, rec.doc_diff_vat or 0.0)

            rec.elig_base_amount = remaining_base
            rec.elig_vat_amount = remaining_vat
            # TVA rămâne "auto" (dacă user-ul schimbă baza, se va recalcula)
            rec.elig_vat_manual = False

    @api.constrains('document_line_id', 'elig_base_amount', 'elig_vat_amount', 'settlement_id')
    def _check_document_line_in_same_implementation_and_limits(self):
        for rec in self:
            if not rec.document_line_id or not rec.settlement_id:
                continue

            if rec.document_line_id.document_id.implementation_id != rec.settlement_id.implementation_id:
                raise ValidationError(_("Linia de document selectată nu aparține implementării curente."))

            if not rec.implementation_id:
                continue

            coef = rec.neramb_coef or 0.0
            max_base = (rec.document_line_id.elig_base_amount or 0.0) * coef
            max_vat = (rec.document_line_id.elig_vat_amount or 0.0) * coef

            other_lines = self.env['project.settlement.line'].search([
                ('settlement_id.implementation_id', '=', rec.implementation_id.id),
                ('document_line_id', '=', rec.document_line_id.id),
                ('id', '!=', rec.id),
            ])
            total_base = (rec.elig_base_amount or 0.0) + sum(other_lines.mapped('elig_base_amount') or [0.0])
            total_vat = (rec.elig_vat_amount or 0.0) + sum(other_lines.mapped('elig_vat_amount') or [0.0])

            if total_base > (max_base + 0.0001):
                raise ValidationError(_("Depășești nerambursabilul pe Bază pentru această linie document."))
            if total_vat > (max_vat + 0.0001):
                raise ValidationError(_("Depășești nerambursabilul pe TVA pentru această linie document."))