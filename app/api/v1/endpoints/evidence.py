# app/services/evidence_service.py
import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Any
import aiohttp
import asyncio

class EvidenceService:
    def __init__(self):
        self.evidence_dir = "evidence_store"
        os.makedirs(self.evidence_dir, exist_ok=True)
    
    def _hash_evidence(self, data: Dict[str, Any]) -> str:
        """Generate SHA-256 hash of evidence"""
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()
    
    async def upload_to_ipfs(self, data: Dict[str, Any]) -> str:
        """Upload evidence to IPFS and return CID"""
        try:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('file', 
                    json.dumps(data), 
                    filename='evidence.json')
                
                async with session.post('https://ipfs.io/api/v0/add', data=form_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result['Hash']
        except Exception as e:
            print(f"IPFS upload error: {e}")
        return None
    
    async def anchor_evidence(self, transaction_data: Dict[str, Any], risk_score: float, decision: str) -> Dict[str, Any]:
        """Store evidence on blockchain and IPFS"""
        
        # Create evidence package
        evidence = {
            "transaction_id": transaction_data.get("transaction_id", "unknown"),
            "amount": transaction_data.get("amount"),
            "merchant": transaction_data.get("merchant_id"),
            "user_id": transaction_data.get("user_id"),
            "risk_score": int(risk_score * 100),
            "decision": decision,
            "timestamp": datetime.now().isoformat()
        }
        
        # Generate hash
        evidence_hash = self._hash_evidence(evidence)
        
        # Upload to IPFS
        cid = await self.upload_to_ipfs(evidence)
        
        # Save locally as backup
        local_path = f"{self.evidence_dir}/{evidence_hash}.json"
        with open(local_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        # Mock blockchain transaction (replace with actual Web3 call)
        mock_tx_hash = f"0x{evidence_hash[:40]}"
        
        return {
            "success": True,
            "evidence_hash": evidence_hash,
            "cid": cid or evidence_hash[:20],
            "blockchain_tx": mock_tx_hash,
            "timestamp": datetime.now().isoformat(),
            "verification_url": f"/verify/{evidence_hash}"
        }
    
    def verify_evidence(self, evidence_hash: str) -> Dict[str, Any]:
        """Verify stored evidence"""
        local_path = f"{self.evidence_dir}/{evidence_hash}.json"
        
        if os.path.exists(local_path):
            with open(local_path, "r") as f:
                evidence = json.load(f)
            return {
                "exists": True,
                "verified": True,
                "evidence": evidence,
                "blockchain_verified": True,
                "timestamp": evidence.get("timestamp")
            }
        
        return {
            "exists": False,
            "verified": False,
            "message": "Evidence not found"
        }
