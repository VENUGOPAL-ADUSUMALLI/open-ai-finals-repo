def present_profile_success(user) -> dict:

    return {
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'phone_number': user.phone_number,
            'age': user.age,
            'gender': user.gender,
            'address': user.address,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None,
        },
    }
