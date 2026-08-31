#!/usr/bin/env python
"""Test script to verify all imports work correctly"""

try:
    print('Testing imports...')
    
    print('1. Testing direct_link_router...')
    from ppc-backend.app.routers import direct_link_router
    print('✓ direct_link_router imported successfully')
    
    print('2. Testing redirect_chain_router...')
    from ppc-backend.app.routers import redirect_chain_router  
    print('✓ redirect_chain_router imported successfully')
    
    print('3. Testing public_stats_router...')
    from ppc-backend.app.routers import public_stats_router
    print('✓ public_stats_router imported successfully')
    
    print('4. Testing main app...')
    from ppc-backend.app.main import app
    print('✓ main app imported successfully')
    
    print('\n🎉 All imports successful!')
    
except Exception as e:
    print(f'❌ Import error: {e}')
    import traceback
    traceback.print_exc()