# -*- coding: utf-8 -*-
import os
import re
import base64
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


def _safe_filename(name: str) -> str:
    name = (name or '').strip()
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)  # windows forbidden
    name = re.sub(r'\s+', ' ', name).strip()
    return name or 'fisier'


class ProjectFile(models.Model):
    _name = 'project.file'
    _description = 'Fișier proiect (pe disk)'
    _order = 'create_date desc, id desc'

    # =========================================================
    # Strict: fișierele există DOAR pe implementare (A)
    # funding_project_id este derivat din implementation_id
    # =========================================================
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
        compute='_compute_funding_project_id',
        store=True,
        readonly=True,
        index=True,
    )

    @api.depends('implementation_id')
    def _compute_funding_project_id(self):
        for rec in self:
            rec.funding_project_id = rec.implementation_id.funding_project_id if rec.implementation_id else False

    category = fields.Selection([
        ('funding_contract', 'Contract finanțare'),
        ('plan_achizitii', 'Plan achiziții'),
        ('plan_activitati', 'Plan activități'),
        ('deviz', 'Deviz'),
        ('contract', 'Contract implementare'),
        ('document', 'Document'),
        ('settlement', 'Decontare'),
        ('other', 'Altele'),
    ], string='Categorie', required=True, default='other', index=True)

    # “de unde e apelat”
    res_model = fields.Char(string='Model', index=True)
    res_id = fields.Integer(string='ID în model', index=True)

    original_filename = fields.Char(string='Nume original')
    standard_filename = fields.Char(string='Nume standard', compute='_compute_standard_filename', store=True)

    stored_path = fields.Char(string='Cale pe disk', readonly=True)

    # upload transient
    upload = fields.Binary(string='Fișier (upload)', attachment=False)
    upload_filename = fields.Char(string='Nume fișier upload')

    note = fields.Text(string='Observații')

    # =========================================================
    # Helpers
    # =========================================================
    @api.depends('category', 'funding_project_id.cod', 'res_id')
    def _compute_standard_filename(self):
        for rec in self:
            code = rec.funding_project_id.cod if rec.funding_project_id else 'PROIECT'
            code = _safe_filename(code)

            # preferăm res_id (ex: id contract / document / decontare),
            # altfel folosim id-ul fișierului
            suffix = str(rec.res_id or rec.id or '')

            if rec.category == 'contract':
                base = f"Contract_{code}_{suffix}"
            elif rec.category == 'document':
                base = f"Document_{code}_{suffix}"
            elif rec.category == 'settlement':
                base = f"Decontare_{code}_{suffix}"
            elif rec.category == 'deviz':
                base = f"Deviz_{code}_{suffix}"
            elif rec.category == 'funding_contract':
                base = f"ContractFinantare_{code}_{suffix}"
            elif rec.category == 'plan_achizitii':
                base = f"PlanAchizitii_{code}_{suffix}"
            elif rec.category == 'plan_activitati':
                base = f"PlanActivitati_{code}_{suffix}"
            else:
                base = f"Fisier_{code}_{suffix}"

            ext = ''
            fn = rec.upload_filename or rec.original_filename or ''
            if '.' in fn:
                ext = '.' + fn.split('.')[-1].lower()

            rec.standard_filename = _safe_filename(base) + ext

    def _get_root_path(self):
        root = (self.env['ir.config_parameter'].sudo().get_param('project_implementation.files_root') or '').strip()
        if not root:
            raise ValidationError(_(
                "Nu este setată calea de stocare.\n"
                "Setează parametrul: project_implementation.files_root\n"
                "Exemplu: D:\\Proiecte  sau  \\\\server\\share\\Proiecte"
            ))
        return root

    def _get_project_folder(self):
        self.ensure_one()
        if not self.funding_project_id or not self.funding_project_id.cod:
            raise ValidationError(_("Nu se poate determina codul proiectului (project.funding.cod)."))
        root = self._get_root_path()
        return os.path.join(root, _safe_filename(self.funding_project_id.cod))

    def _ensure_folder(self, folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            raise ValidationError(_("Nu pot crea folderul: %s\n%s") % (folder, e))

    def _get_category_folder(self):
        self.ensure_one()
        project_folder = self._get_project_folder()
        self._ensure_folder(project_folder)

        subfolder_map = {
            'funding_contract': '01_ContractFinantare',
            'plan_achizitii': '02_PlanAchizitii',
            'plan_activitati': '03_PlanActivitati',
            'deviz': '04_Deviz',
            'contract': '05_Contracte',
            'document': '06_Documente',
            'settlement': '07_Decontari',
            'other': '99_Altele',
        }
        folder = os.path.join(project_folder, subfolder_map.get(self.category, '99_Altele'))
        self._ensure_folder(folder)
        return folder

    def _assert_same_project(self):
        """Extra safety: nu permitem mismatch între implementare și funding."""
        for rec in self:
            if not rec.implementation_id:
                raise ValidationError(_("Fișierul trebuie să aibă o implementare."))

            # funding_project_id este compute+store; dacă încă nu e calculat, nu blocăm
            if rec.funding_project_id and rec.implementation_id.funding_project_id != rec.funding_project_id:
                raise ValidationError(_("Inconsistență: proiectul finanțat nu corespunde implementării."))

    # =========================================================
    # CRUD
    # =========================================================
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._assert_same_project()
        for rec in recs:
            if rec.upload:
                rec._save_upload_to_disk_and_clear()
        return recs

    def write(self, vals):
        res = super().write(vals)
        self._assert_same_project()
        for rec in self:
            if rec.upload:
                rec._save_upload_to_disk_and_clear()
        return res

    def unlink(self):
        """
        Nu ștergem automat fișierul de pe disk (pentru siguranță).
        Dacă vrei, putem adăuga un buton separat "Șterge și de pe disk".
        """
        return super().unlink()

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context or {}

        # fallback: preluăm orice default_* util ca să funcționeze crearea din Contract/Document/Decontare
        for field_name in ('implementation_id', 'category', 'res_model', 'res_id'):
            key = f'default_{field_name}'
            if ctx.get(key) and not vals.get(field_name):
                vals[field_name] = ctx.get(key)

        return vals

    # =========================================================
    # Disk operations
    # =========================================================
    def _save_upload_to_disk_and_clear(self):
        self.ensure_one()
        if not self.upload:
            return

        folder = self._get_category_folder()

        filename = self.standard_filename or _safe_filename(self.upload_filename or self.original_filename or 'fisier')
        full_path = os.path.join(folder, filename)

        try:
            data = base64.b64decode(self.upload)
        except Exception as e:
            raise ValidationError(_("Fișier invalid (base64 decode a eșuat): %s") % e)

        try:
            with open(full_path, 'wb') as f:
                f.write(data)
        except Exception as e:
            raise ValidationError(_("Nu pot scrie fișierul pe disk:\n%s\n%s") % (full_path, e))

        # curățăm binarul din DB
        self.sudo().write({
            'stored_path': full_path,
            'original_filename': self.upload_filename or self.original_filename or filename,
            'upload': False,
            'upload_filename': False,
        })

    # =========================================================
    # Actions
    # =========================================================
    def action_download(self):
        self.ensure_one()
        if not self.stored_path:
            raise ValidationError(_("Acest fișier nu are cale salvată pe disk."))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/project_files/download/{self.id}',
            'target': 'self',
        }