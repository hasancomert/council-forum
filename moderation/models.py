from django.db import models


class Hideable(models.Model):
    """Moderasyonla gizlenebilen içeriğin ortak atası: Comment, Topic, BaseProposal. Silmeden ayrı alan;
    veritabanından bir şey silinmez. Gizli içerik donar ve listelerden çıkar, metnini yalnızca sahibi ve
    yöneticiler görür. Bu uygulama comments, topics ve voting'i modellerde import etmez; döngü olmaz.
    """
    OWNER = 'author'  # içeriğin sahibi olan alan (öneride 'proposer')
    is_hidden = models.BooleanField('moderasyonla gizli', default=False)

    class Meta:
        abstract = True

    @property
    def owner_id(self):
        return getattr(self, f'{self.OWNER}_id')

    @property
    def owner(self):
        return getattr(self, self.OWNER)

    def hidden_from(self, user):
        """Gizli ve kullanıcı ne sahibi ne yönetici: metin yerine "moderasyonla gizlendi" yazılır."""
        return self.is_hidden and not (user.is_authenticated and (user.is_moderator or user.pk == self.owner_id))

    def set_hidden(self, hidden):
        """Gizler ya da gizlemeyi kaldırır; kaydı moderasyon görünümü yazar."""
        self.is_hidden = hidden
        self.save(update_fields=['is_hidden'])
