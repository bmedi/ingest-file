import logging
import os
import pathlib
import subprocess

from followthemoney.helpers import entity_filename

from ingestors.support.cache import CacheSupport
from ingestors.support.temp import TempFileSupport
from ingestors.exc import ProcessingException

log = logging.getLogger(__name__)

TIMEOUT = 3600  # seconds
CONVERT_RETRIES = 5


class DocumentConvertSupport(CacheSupport, TempFileSupport):
    """Provides helpers for UNO document conversion."""

    def document_to_pdf(self, unique_tmpdir, file_path, entity):
        key = self.cache_key("pdf", entity.first("contentHash"))
        pdf_hash = self.tags.get(key)
        if pdf_hash is not None:
            file_name = entity_filename(entity, extension="pdf")
            path = self.manager.load(pdf_hash, file_name=file_name)
            if path is not None:
                log.info("Using PDF cache: %s", file_name)
                entity.set("pdfHash", pdf_hash)
                return path

        pdf_file = self._document_to_pdf(unique_tmpdir, file_path, entity)
        if pdf_file is not None:
            content_hash = self.manager.store(pdf_file)
            entity.set("pdfHash", content_hash)
            self.tags.set(key, content_hash)
        return pdf_file

    def _document_to_pdf(self, unique_tmpdir, file_path, entity, timeout=TIMEOUT):
        """Converts an office document to PDF."""
        file_name = entity_filename(entity)
        log.info("Converting [%s] to PDF", entity)

        pdf_output_dir = os.path.join(unique_tmpdir, "out")
        libreoffice_profile_dir = os.path.join(unique_tmpdir, "profile")
        pathlib.Path(pdf_output_dir).mkdir(parents=True)
        pathlib.Path(libreoffice_profile_dir).mkdir(parents=True)

        cmd = [
            "/usr/bin/libreoffice",
            '"-env:UserInstallation=file://{}"'.format(libreoffice_profile_dir),
            "--nologo",
            "--headless",
            "--nocrashreport",
            "--nodefault",
            "--norestore",
            "--nolockcheck",
            "--invisible",
            "--convert-to",
            "pdf",
            "--outdir",
            pdf_output_dir,
            file_path,
        ]
        try:
            for attempt in range(1, CONVERT_RETRIES):
                log.info(
                    f"Starting LibreOffice: %s with timeout %s attempt #{attempt}/{CONVERT_RETRIES}",
                    cmd,
                    timeout,
                )
                try:
                    subprocess.run(cmd, timeout=timeout, check=True)
                except Exception as e:
                    log.info(
                        f"Could not be converted to PDF (attempt {attempt}/{CONVERT_RETRIES}): {e}"
                    )
                    continue

                for file_name in os.listdir(pdf_output_dir):
                    if not file_name.endswith(".pdf"):
                        continue
                    out_file = os.path.join(pdf_output_dir, file_name)
                    if os.stat(out_file).st_size == 0:
                        continue
                    log.info(f"Successfully converted {out_file}")
                    return out_file
            raise ProcessingException(
                f"Could not be converted to PDF (attempt #{attempt}/{CONVERT_RETRIES})"
            )
        except Exception as e:
            raise ProcessingException("Could not be converted to PDF") from e
