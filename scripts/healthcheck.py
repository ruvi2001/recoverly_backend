"""
Health check script for all services
"""

import asyncio
import httpx
from typing import Dict, List

SERVICES = [
    {"name": "Social Service", "url": "http://localhost:8003/api/health"},
    {"name": "Risk Service", "url": "http://localhost:8001/api/health"},
    {"name": "Reco Service", "url": "http://localhost:8002/api/health"},
    {"name": "Causal Service", "url": "http://localhost:8004/api/health"},
]


async def check_service(service: Dict) -> Dict:
    """Check if a service is healthy"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(service["url"])
            if response.status_code == 200:
                data = response.json()
                return {
                    "name": service["name"],
                    "status": "✓ Healthy",
                    "details": data
                }
            else:
                return {
                    "name": service["name"],
                    "status": f"✗ Unhealthy (HTTP {response.status_code})",
                    "details": None
                }
    except httpx.ConnectError:
        return {
            "name": service["name"],
            "status": "✗ Not Running",
            "details": None
        }
    except Exception as e:
        return {
            "name": service["name"],
            "status": f"✗ Error: {str(e)}",
            "details": None
        }


async def check_all_services():
    """Check health of all services"""
    print("=" * 60)
    print("Recoverly Platform - Health Check")
    print("=" * 60)
    print()
    
    tasks = [check_service(service) for service in SERVICES]
    results = await asyncio.gather(*tasks)
    
    for result in results:
        print(f"{result['name']:20} {result['status']}")
        if result['details']:
            print(f"  Version: {result['details'].get('version', 'unknown')}")
            print(f"  Database: {result['details'].get('database', 'unknown')}")
        print()
    
    print("=" * 60)
    
    # Summary
    healthy = sum(1 for r in results if "Healthy" in r['status'])
    total = len(results)
    print(f"Summary: {healthy}/{total} services healthy")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(check_all_services())
