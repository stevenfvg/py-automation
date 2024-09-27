from flask_restx import Namespace, Resource, fields
from automation import PyAutomation, Roles, Role
from automation.extensions.api import api
from automation.extensions import _api as Api


ns = Namespace('Roles', description='Roles')
app = PyAutomation()

create_role_model = api.model("create_role_model", {
    'name': fields.String(required=True, description='Role Name'),
    'level': fields.Integer(required=True, description='Role Level')
})

@ns.route('/add')
class CreateRoleResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(create_role_model)
    def post(self):
        """User signup"""
        role = Role(**api.payload)
        roles = Roles()
        role_id = roles.add(role=role)
        
        if role_id:

            return role.serialize(), 200