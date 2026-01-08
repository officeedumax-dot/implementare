# -*- coding: utf-8 -*-
import os
from odoo import http
from odoo.http import request


class ProjectFilesController(http.Controller):

    @http.route('/project_files/download/<int:file_id>', type='http', auth='user')
    def download_project_file(self, file_id, **kwargs):
        rec = request.env['project.file'].sudo().browse(file_id)
        if not rec.exists() or not rec.stored_path:
            return request.not_found()

        path = rec.stored_path
        if not os.path.isfile(path):
            return request.not_found()

        filename = os.path.basename(path)
        with open(path, 'rb') as f:
            content = f.read()

        headers = [
            ('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', f'attachment; filename="{filename}"'),
        ]
        return request.make_response(content, headers=headers)