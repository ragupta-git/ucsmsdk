"""This module contains the general information for AdaptorEthArfsProfile ManagedObject."""

from ...ucsmo import ManagedObject
from ...ucscoremeta import MoPropertyMeta, MoMeta
from ...ucsmeta import VersionMeta


class AdaptorEthArfsProfileConsts:
    ACCELARATED_RFS_DISABLED = "disabled"
    ACCELARATED_RFS_ENABLED = "enabled"


class AdaptorEthArfsProfile(ManagedObject):
    """This is AdaptorEthArfsProfile class."""

    consts = AdaptorEthArfsProfileConsts()
    naming_props = set([])

    mo_meta = MoMeta("AdaptorEthArfsProfile", "adaptorEthArfsProfile", "eth-arfs", VersionMeta.Version222c, "InputOutput", 0x3f, [], ["admin", "ls-config-policy", "ls-network", "ls-server-policy"], [u'adaptorHostEthIf', u'adaptorHostEthIfProfile'], [], ["Get", "Set"])

    prop_meta = {
        "accelarated_rfs": MoPropertyMeta("accelarated_rfs", "accelaratedRFS", "string", VersionMeta.Version222c, MoPropertyMeta.READ_WRITE, 0x2, None, None, None, ["disabled", "enabled"], []),
        "child_action": MoPropertyMeta("child_action", "childAction", "string", VersionMeta.Version222c, MoPropertyMeta.INTERNAL, 0x4, None, None, r"""((deleteAll|ignore|deleteNonPresent),){0,2}(deleteAll|ignore|deleteNonPresent){0,1}""", [], []),
        "dn": MoPropertyMeta("dn", "dn", "string", VersionMeta.Version222c, MoPropertyMeta.READ_ONLY, 0x8, 0, 256, None, [], []),
        "rn": MoPropertyMeta("rn", "rn", "string", VersionMeta.Version222c, MoPropertyMeta.READ_ONLY, 0x10, 0, 256, None, [], []),
        "sacl": MoPropertyMeta("sacl", "sacl", "string", VersionMeta.Version302c, MoPropertyMeta.READ_ONLY, None, None, None, r"""((none|del|mod|addchild|cascade),){0,4}(none|del|mod|addchild|cascade){0,1}""", [], []),
        "status": MoPropertyMeta("status", "status", "string", VersionMeta.Version222c, MoPropertyMeta.READ_WRITE, 0x20, None, None, r"""((removed|created|modified|deleted),){0,3}(removed|created|modified|deleted){0,1}""", [], []),
    }

    prop_map = {
        "accelaratedRFS": "accelarated_rfs", 
        "childAction": "child_action", 
        "dn": "dn", 
        "rn": "rn", 
        "sacl": "sacl", 
        "status": "status", 
    }

    def __init__(self, parent_mo_or_dn, **kwargs):
        self._dirty_mask = 0
        self.accelarated_rfs = None
        self.child_action = None
        self.sacl = None
        self.status = None

        ManagedObject.__init__(self, "AdaptorEthArfsProfile", parent_mo_or_dn, **kwargs)
