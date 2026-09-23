"""Inspect or reparse an archived ShareData document with a registered parser."""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.db.engine import DBEngine
from modules.data.ingestion_evidence import (SHAREDATA_PARSERS,parse_sharedata_document,
    reparse_sharedata_document)

async def run(document_id: UUID, version: str, apply: bool):
    if version not in SHAREDATA_PARSERS:
        raise ValueError('Parser implementation must be registered in ingestion_evidence.py')
    try:
        rows=await DBEngine.fetch('SELECT source,document_type,raw_content FROM source_documents WHERE id=$1',document_id)
        if not rows or rows[0]['source']!='sharedata':
            raise ValueError('ShareData document not found')
        parsed=SHAREDATA_PARSERS[version](rows[0]['document_type'].split(':',1)[0],rows[0]['raw_content'])
        if not apply:
            return {'mode':'dry_run','document_id':str(document_id),'parser_version':version,'observations':len(parsed)}
        count=await reparse_sharedata_document(document_id,parser_version=version)
        return {'mode':'applied','document_id':str(document_id),'parser_version':version,'new_observations':count}
    finally:
        await DBEngine.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('document_id',type=UUID)
    parser.add_argument('--parser-version',required=True)
    parser.add_argument('--apply',action='store_true',help='Append new observations and refresh projection; default is dry run')
    args=parser.parse_args()
    print(asyncio.run(run(args.document_id,args.parser_version,args.apply)))
